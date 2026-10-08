"""jarvis/speech.py — Dedicated High-Fidelity Text-To-Speech engine using Microsoft Edge-TTS with persistent caching."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import logging
import os
import queue
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Single consistent voice definition
DEFAULT_VOICE = "en-GB-RyanNeural"
CACHE_DIR = Path("data/tts_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

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


def _play_audio_file(filepath: str) -> bool:
    """Play an audio file (.mp3) synchronously with interrupt support."""
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return False

    # 1. Windows MCI (Zero latency native playback)
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
                        time.sleep(0.02)
                    return True
                finally:
                    winmm.mciSendStringW(f'close {alias}', None, 0, None)
            else:
                logger.debug("Native MCI open error code %d, trying sounddevice fallback.", res)
        except Exception as e:
            logger.debug("Native MCI playback error: %s", e)

    # 2. SoundDevice / Pydub fallback
    try:
        import numpy as np
        import sounddevice as sd
        from pydub import AudioSegment

        audio = AudioSegment.from_file(filepath)
        samples = np.array(audio.get_array_of_samples())
        if audio.channels == 2:
            samples = samples.reshape((-1, 2))
        data = samples.astype(np.float32) / (2**15 if audio.sample_width == 2 else 2**31)

        sd.play(data, audio.frame_rate)
        while sd.get_stream() and sd.get_stream().active:
            if _stop_playback_event.is_set():
                sd.stop()
                break
            time.sleep(0.02)
        return True
    except Exception as exc:
        logger.warning("Audio playback failed: %s", exc)
        return False


def _get_cache_path(text: str, voice: str, rate: str, pitch: str) -> Path:
    """Generate a persistent cache file path for the utterance."""
    cache_key = f"{voice}_{rate}_{pitch}_{text.strip()}".encode("utf-8")
    filename = f"{hashlib.md5(cache_key).hexdigest()}.mp3"
    return CACHE_DIR / filename


def _synthesize_edge_tts(text: str, voice: str, rate: str, pitch: str, outfile: str) -> bool:
    """Synthesize speech using Microsoft Edge-TTS with retry."""
    import edge_tts

    for attempt in range(1, 4):
        try:
            async def _run():
                communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
                await communicate.save(outfile)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(asyncio.wait_for(_run(), timeout=8.0))
            loop.close()

            if os.path.exists(outfile) and os.path.getsize(outfile) > 0:
                return True
        except Exception as exc:
            logger.warning("Edge-TTS synthesis attempt %d failed: %s", attempt, exc)
            time.sleep(0.2 * attempt)

    return False


def _tts_worker() -> None:
    """Dedicated background thread to handle TTS tasks sequentially using single consistent voice."""
    if sys.platform == "win32":
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass

    from jarvis.utils import load_config
    try:
        config = load_config()
    except Exception:
        config = {}

    voice = config.get("edge_tts_voice") or DEFAULT_VOICE
    rate = config.get("edge_tts_rate", "+0%")
    pitch = config.get("edge_tts_pitch", "+0Hz")

    logger.info("Jarvis TTS Engine active: %s (Single Voice Locked)", voice)

    while True:
        item = _speech_queue.get()
        if item is None:
            break
        text, done_event = item

        # Clear stop signal before starting new utterance
        _stop_playback_event.clear()
        _speaking_event.set()

        try:
            # Check disk cache first for 0ms response
            cache_file = _get_cache_path(text, voice, rate, pitch)
            audio_ready = False

            if cache_file.exists() and cache_file.stat().st_size > 0:
                audio_ready = True
                audio_file_to_play = str(cache_file)
            else:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                    temp_mp3 = tf.name

                if _synthesize_edge_tts(text, voice, rate, pitch, temp_mp3):
                    try:
                        # Save into persistent cache
                        import shutil
                        shutil.copyfile(temp_mp3, str(cache_file))
                        audio_file_to_play = str(cache_file)
                        audio_ready = True
                    except Exception:
                        audio_file_to_play = temp_mp3
                        audio_ready = True
                    finally:
                        if os.path.exists(temp_mp3):
                            try:
                                os.remove(temp_mp3)
                            except Exception:
                                pass

            if audio_ready and not _stop_playback_event.is_set():
                _play_audio_file(audio_file_to_play)

        except Exception as exc:
            logger.error("TTS worker unexpected error: %s", exc)
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
    Speak the given text aloud using the dedicated RyanNeural voice.
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
