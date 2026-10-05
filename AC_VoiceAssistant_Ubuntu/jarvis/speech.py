"""jarvis/speech.py — Multi-engine Text-To-Speech pipeline with Edge-TTS, Kokoro, Piper, and Linux/Windows audio players."""

from __future__ import annotations

import asyncio
import ctypes
import io
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Thread-safe queue to pass text and done events to the TTS thread
_speech_queue: queue.Queue[tuple[str, threading.Event | None] | None] = queue.Queue()

_speaking_event = threading.Event()
_stop_playback_event = threading.Event()
_active_playback_process: Optional[subprocess.Popen] = None


def is_speaking() -> bool:
    """Return True if the assistant is currently speaking."""
    return _speaking_event.is_set()


def stop_speaking() -> None:
    """Immediately stop active audio playback and clear pending speech queue (Barge-in)."""
    global _active_playback_process
    _stop_playback_event.set()
    _speaking_event.clear()

    # 1. Stop SoundDevice playback
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass

    # 2. Terminate active CLI playback process if running on Linux
    if _active_playback_process is not None:
        try:
            _active_playback_process.terminate()
            _active_playback_process.kill()
        except Exception:
            pass
        _active_playback_process = None

    # 3. Stop Windows MCI playback if active on Windows
    if sys.platform == "win32":
        try:
            ctypes.windll.winmm.mciSendStringW("stop all", None, 0, None)
            ctypes.windll.winmm.mciSendStringW("close all", None, 0, None)
        except Exception:
            pass

    # 4. Drain pending sentences in speech queue
    while not _speech_queue.empty():
        try:
            item = _speech_queue.get_nowait()
            if item is not None:
                _, done_event = item
                if done_event is not None:
                    done_event.set()
            _speech_queue.task_done()
        except Exception:
            break


def _play_audio_file(filepath: str) -> bool:
    """Play an audio file (.mp3 / .wav) synchronously with real-time interrupt support across Linux and Windows."""
    global _active_playback_process
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return False

    # A. Python sounddevice / soundfile / pydub in-memory playback (Cross-platform)
    try:
        import sounddevice as sd
        import soundfile as sf
        import numpy as np

        # For MP3 files, convert to raw audio via pydub if soundfile doesn't support direct mp3 reading
        try:
            data, fs = sf.read(filepath, dtype='float32')
        except Exception:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(filepath)
            samples = np.array(audio.get_array_of_samples())
            if audio.channels == 2:
                samples = samples.reshape((-1, 2))
            data = samples.astype(np.float32) / (2**15 if audio.sample_width == 2 else 2**31)
            fs = audio.frame_rate

        sd.play(data, fs)
        while sd.get_stream() and sd.get_stream().active:
            if _stop_playback_event.is_set():
                sd.stop()
                return True
            time.sleep(0.02)
        return True
    except Exception as e:
        logger.debug("SoundDevice/SoundFile playback unavailable or failed: %s. Trying CLI players...", e)

    # B. Linux CLI Players fallback (ffplay, mpv, mpg123, paplay, aplay)
    if sys.platform != "win32":
        players = [
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", filepath],
            ["mpv", "--no-video", "--really-quiet", filepath],
            ["mpg123", "-q", filepath],
            ["paplay", filepath],
            ["aplay", "-q", filepath]
        ]
        for cmd in players:
            if shutil.which(cmd[0]):
                try:
                    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    _active_playback_process = proc
                    while proc.poll() is None:
                        if _stop_playback_event.is_set():
                            proc.terminate()
                            try:
                                proc.kill()
                            except Exception:
                                pass
                            _active_playback_process = None
                            return True
                        time.sleep(0.03)
                    _active_playback_process = None
                    return True
                except Exception as cli_err:
                    logger.debug("CLI player %s failed: %s", cmd[0], cli_err)

    # C. Windows MCI Fallback
    if sys.platform == "win32":
        alias = f"jarvis_tts_{os.getpid()}_{time.time_ns()}"
        winmm = ctypes.windll.winmm
        clean_path = os.path.normpath(filepath)
        try:
            res = winmm.mciSendStringW(f'open "{clean_path}" type mpegvideo alias {alias}', None, 0, None)
            if res == 0:
                try:
                    winmm.mciSendStringW(f'play {alias}', None, 0, None)
                    status_buf = ctypes.create_unicode_buffer(128)
                    while True:
                        if _stop_playback_event.is_set():
                            winmm.mciSendStringW(f'stop {alias}', None, 0, None)
                            return True
                        winmm.mciSendStringW(f'status {alias} mode', status_buf, 128, None)
                        if status_buf.value.lower() in ("stopped", ""):
                            break
                        time.sleep(0.03)
                    return True
                finally:
                    winmm.mciSendStringW(f'close {alias}', None, 0, None)
        except Exception as e:
            logger.warning("Windows MCI audio playback failed: %s", e)

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
            loop.run_until_complete(asyncio.wait_for(_run(), timeout=8.0))
            loop.close()
        except Exception as e:
            logger.warning("Edge-TTS timed out or connection failed: %s", e)
            return False

        return os.path.exists(outfile) and os.path.getsize(outfile) > 0
    except Exception as exc:
        logger.warning("Edge-TTS synthesis error: %s", exc)
        return False


def _tts_worker() -> None:
    """Dedicated background thread to handle TTS tasks sequentially across engines."""
    if sys.platform == "win32":
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

    tts_engine = config.get("tts_engine", "edge").lower()
    edge_voice = config.get("edge_tts_voice", "en-GB-RyanNeural")
    kokoro_model_path = config.get("kokoro_model", "bin/kokoro/kokoro-v1.0.onnx")
    kokoro_voices_path = config.get("kokoro_voices", "bin/kokoro/voices-v1.0.bin")
    kokoro_voice = config.get("kokoro_voice", "af_heart")
    kokoro_speed = float(config.get("kokoro_speed", 1.0))
    kokoro_lang = config.get("kokoro_lang", "en-us")
    piper_path = config.get("piper_path")
    piper_model = config.get("piper_model")

    # Initialize Kokoro ONNX if configured
    kokoro_instance = None
    if tts_engine in ("kokoro", "kokoro-onnx", "kokoro_onnx"):
        if os.path.exists(kokoro_model_path) and os.path.exists(kokoro_voices_path):
            try:
                from kokoro_onnx import Kokoro
                logger.info("Initializing Kokoro-82M ONNX TTS engine (%s)...", kokoro_voice)
                kokoro_instance = Kokoro(kokoro_model_path, kokoro_voices_path)
                logger.info("Kokoro-82M ONNX initialized successfully.")
            except Exception as e:
                logger.warning("Failed to initialize Kokoro ONNX: %s. Will fallback.", e)

    # Initialize pyttsx3 as universal fallback engine
    engine = None
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        engine.setProperty("volume", 1.0)
    except Exception as exc:
        logger.debug("Failed to initialize fallback pyttsx3 engine: %s", exc)

    while True:
        item = _speech_queue.get()
        if item is None:
            break
        text, done_event = item

        # Clear stop signal before starting new utterance
        _stop_playback_event.clear()
        _speaking_event.set()

        try:
            spoken = False

            # 1. Try Edge-TTS (Default natural neural voice)
            if not spoken and not _stop_playback_event.is_set() and tts_engine in ("edge-tts", "edge_tts", "edge"):
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                    temp_mp3 = tf.name
                try:
                    if _synthesize_edge_tts(text, edge_voice, temp_mp3):
                        if _play_audio_file(temp_mp3):
                            spoken = True
                finally:
                    if os.path.exists(temp_mp3):
                        try:
                            os.remove(temp_mp3)
                        except Exception:
                            pass

            # 2. Try Kokoro-82M ONNX
            if kokoro_instance is not None and not spoken and not _stop_playback_event.is_set() and tts_engine in ("kokoro", "kokoro-onnx", "kokoro_onnx"):
                try:
                    import sounddevice as sd
                    samples, sample_rate = kokoro_instance.create(
                        text,
                        voice=kokoro_voice,
                        speed=kokoro_speed,
                        lang=kokoro_lang
                    )
                    if len(samples) > 0 and not _stop_playback_event.is_set():
                        sd.play(samples, sample_rate)
                        while sd.get_stream() and sd.get_stream().active:
                            if _stop_playback_event.is_set():
                                sd.stop()
                                break
                            time.sleep(0.02)
                        spoken = True
                except Exception as exc:
                    logger.warning("Kokoro synthesis/playback error: %s. Falling back.", exc)

            # 3. Fallback to pyttsx3 / espeak
            if not spoken and not _stop_playback_event.is_set() and engine is not None:
                try:
                    engine.say(text)
                    engine.runAndWait()
                    spoken = True
                except Exception as exc:
                    logger.debug("pyttsx3 runtime error: %s", exc)

            # 4. Fallback directly to espeak-ng CLI if available on Linux
            if not spoken and not _stop_playback_event.is_set() and sys.platform != "win32" and shutil.which("espeak-ng"):
                try:
                    subprocess.run(["espeak-ng", "-s", "160", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    spoken = True
                except Exception:
                    pass

        finally:
            _speaking_event.clear()

        if done_event is not None:
            done_event.set()
        _speech_queue.task_done()


# Start the background TTS thread
_worker_thread = threading.Thread(target=_tts_worker, daemon=True)
_worker_thread.start()


def speak(text: str, block: bool = True) -> None:
    """
    Speak the given text aloud.
    If block=True (default), waits until speech finishes.
    If block=False, queues the speech and returns immediately (non-blocking).
    """
    if not text or not text.strip():
        return

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if not sentences:
        return

    if block:
        for idx, sentence in enumerate(sentences):
            is_last = (idx == len(sentences) - 1)
            done_event = threading.Event() if is_last else None
            _speech_queue.put((sentence, done_event))
            if is_last and done_event is not None:
                done_event.wait()
    else:
        for sentence in sentences:
            _speech_queue.put((sentence, None))


def shutdown() -> None:
    """Stop the TTS background thread cleanly."""
    _speech_queue.put(None)
