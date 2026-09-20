import asyncio
import ctypes
import logging
import os
import queue
import subprocess
import sys
import tempfile
import threading
import pyttsx3

logger = logging.getLogger(__name__)

# Thread-safe queue to pass text and done events to the TTS thread
_speech_queue: queue.Queue[tuple[str, threading.Event | None] | None] = queue.Queue()

_speaking_event = threading.Event()


def is_speaking() -> bool:
    """Return True if the assistant is currently speaking."""
    return _speaking_event.is_set()


def _play_audio_file_native(filepath: str) -> bool:
    """Play an audio file (.mp3 / .wav) synchronously using native Windows MCI."""
    if sys.platform == "win32":
        import time
        alias = f"jarvis_tts_{os.getpid()}_{time.time_ns()}"
        winmm = ctypes.windll.winmm
        clean_path = os.path.normpath(filepath)
        try:
            res = winmm.mciSendStringW(f'open "{clean_path}" type mpegvideo alias {alias}', None, 0, None)
            if res == 0:
                try:
                    winmm.mciSendStringW(f'play {alias} wait', None, 0, None)
                    return True
                finally:
                    winmm.mciSendStringW(f'close {alias}', None, 0, None)
            else:
                logger.warning("Native MCI open returned error code %d", res)
        except Exception as e:
            logger.warning("Native MCI audio playback failed: %s", e)
    return False


def _synthesize_edge_tts(text: str, voice: str, outfile: str) -> bool:
    """Synthesize speech using Microsoft Edge-TTS with bounded timeout."""
    try:
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(outfile)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(asyncio.wait_for(_run(), timeout=6.0))
            loop.close()
        except Exception as e:
            logger.warning("Edge-TTS timed out or connection failed: %s", e)
            return False

        return os.path.exists(outfile) and os.path.getsize(outfile) > 0
    except Exception as exc:
        logger.warning("Edge-TTS synthesis error: %s", exc)
        return False


def _tts_worker() -> None:
    """Dedicated background thread to handle TTS tasks sequentially."""
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass

    # Load configuration
    from jarvis.utils import load_config
    try:
        config = load_config()
    except Exception:
        config = {}

    tts_engine = config.get("tts_engine", "edge-tts").lower()
    edge_voice = config.get("edge_tts_voice", "en-US-GuyNeural")
    piper_path = config.get("piper_path")
    piper_model = config.get("piper_model")

    # Initialize PyAudio if Piper is configured
    p_audio = None
    pyaudio = None
    if tts_engine == "piper" and piper_path and piper_model:
        try:
            import pyaudio
            p_audio = pyaudio.PyAudio()
        except Exception as e:
            print(f"[speech] Failed to initialize PyAudio: {e}")

    # Initialize pyttsx3 as fallback SAPI engine
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        engine.setProperty("volume", 1.0)
    except Exception as exc:
        print(f"[speech] Failed to initialize fallback TTS engine: {exc}")
        engine = None

    while True:
        item = _speech_queue.get()
        if item is None:
            break
        text, done_event = item

        _speaking_event.set()

        try:
            spoken = False

            # 1. Try Edge-TTS (High Quality Neural Cloud Voice)
            if tts_engine in ("edge-tts", "edge_tts", "edge") and not spoken:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                    temp_mp3 = tf.name
                try:
                    if _synthesize_edge_tts(text, edge_voice, temp_mp3):
                        if _play_audio_file_native(temp_mp3):
                            spoken = True
                finally:
                    if os.path.exists(temp_mp3):
                        try:
                            os.remove(temp_mp3)
                        except Exception:
                            pass

            # 2. Try Piper (Local Neural Offline Voice)
            if not spoken and tts_engine == "piper" and p_audio is not None and pyaudio is not None and piper_path and piper_model:
                if os.path.exists(piper_path) and os.path.exists(piper_model):
                    try:
                        command = [
                            str(piper_path),
                            "--model", str(piper_model),
                            "--output-raw"
                        ]
                        process = subprocess.Popen(
                            command,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL
                        )
                        audio_data, _ = process.communicate(input=text.encode("utf-8"))
                        
                        if len(audio_data) > 0:
                            stream = p_audio.open(
                                format=pyaudio.paInt16,
                                channels=1,
                                rate=22050,
                                output=True
                            )
                            stream.write(audio_data)
                            stream.stop_stream()
                            stream.close()
                            spoken = True
                    except Exception as exc:
                        print(f"[speech] Piper error: {exc}. Falling back to pyttsx3.")

            # 3. Fallback to pyttsx3 (SAPI5 on Windows)
            if not spoken and engine is not None:
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception as exc:
                    print(f"[speech] SAPI runtime error: {exc}")
                    try:
                        engine = pyttsx3.init()
                        engine.setProperty("rate", 170)
                        engine.setProperty("volume", 1.0)
                        engine.say(text)
                        engine.runAndWait()
                    except Exception as retry_exc:
                        print(f"[speech] Failed to recover SAPI engine: {retry_exc}")
        finally:
            _speaking_event.clear()

        if done_event is not None:
            done_event.set()
        _speech_queue.task_done()

    # Cleanup PyAudio if it was initialized
    if p_audio is not None:
        try:
            p_audio.terminate()
        except Exception:
            pass


# Start the background TTS thread
_worker_thread = threading.Thread(target=_tts_worker, daemon=True)
_worker_thread.start()


def speak(text: str, block: bool = True) -> None:
    """
    Speak the given text aloud.
    If block=True (default), waits until the speech is finished.
    If block=False, queues the speech and returns immediately (non-blocking).
    """
    if not text.strip():
        return

    import re
    # Split into sentences to allow streaming-like playback latency
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if not sentences:
        return

    if block:
        # Queue all sentences and wait for the last one to complete
        for idx, sentence in enumerate(sentences):
            is_last = (idx == len(sentences) - 1)
            done_event = threading.Event() if is_last else None
            _speech_queue.put((sentence, done_event))
            if is_last and done_event is not None:
                done_event.wait()
    else:
        # Non-blocking queue
        for sentence in sentences:
            _speech_queue.put((sentence, None))


def shutdown() -> None:
    """Stop the TTS background thread cleanly."""
    _speech_queue.put(None)



