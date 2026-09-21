"""jarvis/speech.py — Multi-engine Text-To-Speech pipeline with Kokoro-82M ONNX, Edge-TTS, Piper, and pyttsx3."""

from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import queue
import re
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


def is_speaking() -> bool:
    """Return True if the assistant is currently speaking."""
    return _speaking_event.is_set()


def stop_speaking() -> None:
    """Immediately stop active audio playback and clear pending speech queue (Barge-in)."""
    _stop_playback_event.set()
    _speaking_event.clear()

    # 1. Stop SoundDevice playback
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass

    # 2. Stop Windows MCI playback if active
    if sys.platform == "win32":
        try:
            ctypes.windll.winmm.mciSendStringW("stop all", None, 0, None)
            ctypes.windll.winmm.mciSendStringW("close all", None, 0, None)
        except Exception:
            pass

    # 3. Drain pending sentences in speech queue
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


def _play_audio_file_native(filepath: str) -> bool:
    """Play an audio file (.mp3 / .wav) synchronously using native Windows MCI with interrupt support."""
    if sys.platform == "win32":
        alias = f"jarvis_tts_{os.getpid()}_{time.time_ns()}"
        winmm = ctypes.windll.winmm
        clean_path = os.path.normpath(filepath)
        try:
            res = winmm.mciSendStringW(f'open "{clean_path}" type mpegvideo alias {alias}', None, 0, None)
            if res == 0:
                try:
                    winmm.mciSendStringW(f'play {alias}', None, 0, None)
                    # Poll status in chunks to allow interruption
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
    """Dedicated background thread to handle TTS tasks sequentially across engines."""
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

    tts_engine = config.get("tts_engine", "kokoro").lower()
    edge_voice = config.get("edge_tts_voice", "en-US-GuyNeural")
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
        else:
            logger.info("Kokoro model files not found at %s. Run setup_kokoro.py to activate.", kokoro_model_path)

    # Initialize PyAudio if Piper is configured
    p_audio = None
    pyaudio = None
    if tts_engine == "piper" and piper_path and piper_model:
        try:
            import pyaudio
            p_audio = pyaudio.PyAudio()
        except Exception as e:
            logger.debug("Failed to initialize PyAudio: %s", e)

    # Initialize pyttsx3 as universal fallback SAPI engine
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        engine.setProperty("volume", 1.0)
    except Exception as exc:
        logger.debug("Failed to initialize fallback SAPI engine: %s", exc)
        engine = None

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

            # 1. If Piper is explicitly selected, try Piper first
            if not spoken and not _stop_playback_event.is_set() and tts_engine == "piper" and piper_path and piper_model:
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

                        if len(audio_data) > 0 and not _stop_playback_event.is_set():
                            try:
                                import numpy as np
                                import sounddevice as sd
                                samples = np.frombuffer(audio_data, dtype=np.int16)
                                sd.play(samples, 22050)
                                while sd.get_stream() and sd.get_stream().active:
                                    if _stop_playback_event.is_set():
                                        sd.stop()
                                        break
                                    time.sleep(0.02)
                                spoken = True
                            except Exception:
                                if p_audio is not None and pyaudio is not None:
                                    stream = p_audio.open(
                                        format=pyaudio.paInt16,
                                        channels=1,
                                        rate=22050,
                                        output=True
                                    )
                                    chunk_sz = 2048
                                    for i in range(0, len(audio_data), chunk_sz):
                                        if _stop_playback_event.is_set():
                                            break
                                        stream.write(audio_data[i:i + chunk_sz])
                                    stream.stop_stream()
                                    stream.close()
                                    spoken = True
                    except Exception as exc:
                        logger.warning("Piper error: %s. Falling back.", exc)

            # 2. Try Kokoro-82M ONNX (Ultra-High-Fidelity Local Neural Voice)
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

            # 3. Try Edge-TTS (High Quality Cloud Voice)
            if not spoken and not _stop_playback_event.is_set() and tts_engine in ("edge-tts", "edge_tts", "edge"):
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

            # 4. Fallback to pyttsx3 (SAPI5 offline Windows engine)
            if not spoken and not _stop_playback_event.is_set() and engine is not None:
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception as exc:
                    logger.debug("SAPI runtime error: %s", exc)
                    try:
                        import pyttsx3
                        engine = pyttsx3.init()
                        engine.setProperty("rate", 170)
                        engine.setProperty("volume", 1.0)
                        engine.say(text)
                        engine.runAndWait()
                    except Exception as retry_exc:
                        logger.debug("Failed to recover SAPI engine: %s", retry_exc)
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
    If block=True (default), waits until speech finishes.
    If block=False, queues the speech and returns immediately (non-blocking).
    """
    if not text or not text.strip():
        return

    # Split into sentences to allow streaming-like playback latency
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
