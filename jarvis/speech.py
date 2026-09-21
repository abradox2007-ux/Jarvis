"""jarvis/speech.py — Multi-engine Text-To-Speech pipeline with Kokoro-82M ONNX, Edge-TTS, Piper, and pyttsx3.

Optimized with background startup pre-warming and pipelined sentence streaming.
"""

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
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Queue for incoming text utterances to be synthesized
# Items: tuple[str, bool, threading.Event | None] -> (sentence, is_last_in_utterance, done_event)
_text_queue: queue.Queue[Optional[tuple[str, bool, threading.Event | None]]] = queue.Queue()

# Queue for synthesized audio chunks ready for playback
# Items: tuple[Any, int, str, bool, threading.Event | None] -> (audio_payload, sample_rate_or_format, engine_type, is_last, done_event)
_audio_queue: queue.Queue[Optional[tuple[Any, Any, str, bool, threading.Event | None]]] = queue.Queue(maxsize=4)

_speaking_event = threading.Event()
_stop_playback_event = threading.Event()
_kokoro_ready_event = threading.Event()


def is_speaking() -> bool:
    """Return True if the assistant is currently speaking."""
    return _speaking_event.is_set()


def stop_speaking() -> None:
    """Immediately stop active audio playback and clear pending queues (Barge-in)."""
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

    # 3. Drain pending text and unblock waiters
    while not _text_queue.empty():
        try:
            item = _text_queue.get_nowait()
            if item is not None:
                _, _, done_event = item
                if done_event is not None:
                    done_event.set()
            _text_queue.task_done()
        except Exception:
            break

    # 4. Drain pending audio queue and unblock waiters
    while not _audio_queue.empty():
        try:
            item = _audio_queue.get_nowait()
            if item is not None:
                _, _, _, _, done_event = item
                if done_event is not None:
                    done_event.set()
            _audio_queue.task_done()
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


def _synthesis_worker() -> None:
    """Worker 1: Pre-synthesizes sentences into audio data ahead of playback."""
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

    kokoro_instance = None
    if tts_engine in ("kokoro", "kokoro-onnx", "kokoro_onnx"):
        if os.path.exists(kokoro_model_path) and os.path.exists(kokoro_voices_path):
            try:
                from kokoro_onnx import Kokoro
                logger.info("Initializing Kokoro-82M ONNX TTS engine (%s)...", kokoro_voice)
                kokoro_instance = Kokoro(kokoro_model_path, kokoro_voices_path)
                # Background Pre-Warming Pass
                logger.info("Pre-warming Kokoro neural session...")
                t_w0 = time.perf_counter()
                kokoro_instance.create("ready", voice=kokoro_voice, speed=kokoro_speed, lang=kokoro_lang)
                logger.info("Kokoro ONNX pre-warmed in %.1fms.", (time.perf_counter() - t_w0) * 1000)
                _kokoro_ready_event.set()
            except Exception as e:
                logger.warning("Failed to initialize Kokoro ONNX: %s. Will fallback.", e)
        else:
            logger.info("Kokoro model files not found at %s.", kokoro_model_path)

    while True:
        item = _text_queue.get()
        if item is None:
            _audio_queue.put(None)
            break

        sentence, is_last, done_event = item

        if _stop_playback_event.is_set():
            if done_event is not None:
                done_event.set()
            _text_queue.task_done()
            continue

        synthesized = False

        # 1. Kokoro-82M ONNX Synthesis
        if kokoro_instance is not None and not _stop_playback_event.is_set():
            try:
                samples, sample_rate = kokoro_instance.create(
                    sentence,
                    voice=kokoro_voice,
                    speed=kokoro_speed,
                    lang=kokoro_lang
                )
                if len(samples) > 0 and not _stop_playback_event.is_set():
                    _audio_queue.put((samples, sample_rate, "kokoro", is_last, done_event))
                    synthesized = True
            except Exception as exc:
                logger.warning("Kokoro synthesis error: %s. Falling back.", exc)

        # 2. Edge-TTS Synthesis Fallback
        if not synthesized and not _stop_playback_event.is_set() and tts_engine in ("edge-tts", "edge_tts", "edge", "kokoro"):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                temp_mp3 = tf.name
            try:
                if _synthesize_edge_tts(sentence, edge_voice, temp_mp3):
                    _audio_queue.put((temp_mp3, 0, "edge-tts", is_last, done_event))
                    synthesized = True
            except Exception:
                pass

        # 3. Piper Offline Synthesis Fallback
        if not synthesized and not _stop_playback_event.is_set() and piper_path and piper_model and os.path.exists(piper_path):
            try:
                cmd = [str(piper_path), "--model", str(piper_model), "--output-raw"]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                raw_audio, _ = proc.communicate(input=sentence.encode("utf-8"))
                if len(raw_audio) > 0 and not _stop_playback_event.is_set():
                    _audio_queue.put((raw_audio, 22050, "piper", is_last, done_event))
                    synthesized = True
            except Exception as exc:
                logger.warning("Piper synthesis error: %s", exc)

        # 4. Fallback SAPI / pyttsx3 direct marker
        if not synthesized and not _stop_playback_event.is_set():
            _audio_queue.put((sentence, 0, "sapi", is_last, done_event))

        _text_queue.task_done()


def _playback_worker() -> None:
    """Worker 2: Plays synthesized audio seamlessly while Worker 1 prepares subsequent sentences."""
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass

    try:
        import sounddevice as sd
    except Exception:
        sd = None

    pyaudio_inst = None
    pyaudio_mod = None
    try:
        import pyaudio
        pyaudio_mod = pyaudio
        pyaudio_inst = pyaudio.PyAudio()
    except Exception:
        pass

    sapi_engine = None
    try:
        import pyttsx3
        sapi_engine = pyttsx3.init()
        sapi_engine.setProperty("rate", 170)
        sapi_engine.setProperty("volume", 1.0)
    except Exception:
        pass

    while True:
        item = _audio_queue.get()
        if item is None:
            break

        payload, sample_rate, engine_type, is_last, done_event = item

        if _stop_playback_event.is_set():
            if done_event is not None:
                done_event.set()
            _audio_queue.task_done()
            continue

        _speaking_event.set()
        try:
            if engine_type == "kokoro" and sd is not None:
                sd.play(payload, sample_rate)
                while sd.get_stream() and sd.get_stream().active:
                    if _stop_playback_event.is_set():
                        sd.stop()
                        break
                    time.sleep(0.02)

            elif engine_type == "edge-tts":
                filepath = payload
                try:
                    _play_audio_file_native(filepath)
                finally:
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                        except Exception:
                            pass

            elif engine_type == "piper" and pyaudio_inst is not None and pyaudio_mod is not None:
                stream = pyaudio_inst.open(
                    format=pyaudio_mod.paInt16,
                    channels=1,
                    rate=int(sample_rate),
                    output=True
                )
                chunk_sz = 2048
                for i in range(0, len(payload), chunk_sz):
                    if _stop_playback_event.is_set():
                        break
                    stream.write(payload[i:i + chunk_sz])
                stream.stop_stream()
                stream.close()

            elif engine_type == "sapi" and sapi_engine is not None:
                sapi_engine.say(str(payload))
                sapi_engine.runAndWait()

        except Exception as err:
            logger.warning("Playback error on %s: %s", engine_type, err)
        finally:
            if done_event is not None:
                done_event.set()
            if is_last or _text_queue.empty() and _audio_queue.empty():
                _speaking_event.clear()

        _audio_queue.task_done()

    if pyaudio_inst is not None:
        try:
            pyaudio_inst.terminate()
        except Exception:
            pass


# Launch dual pipeline threads
_synth_thread = threading.Thread(target=_synthesis_worker, daemon=True, name="TTS-Synthesizer")
_play_thread = threading.Thread(target=_playback_worker, daemon=True, name="TTS-Player")
_synth_thread.start()
_play_thread.start()


def speak(text: str, block: bool = True) -> None:
    """
    Speak the given text aloud using pipelined streaming synthesis.
    If block=True (default), waits until speech finishes.
    If block=False, queues the speech and returns immediately.
    """
    if not text or not text.strip():
        return

    # Split into sentences for pipelined streaming
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if not sentences:
        return

    _stop_playback_event.clear()

    if block:
        last_event: Optional[threading.Event] = None
        for idx, sentence in enumerate(sentences):
            is_last = (idx == len(sentences) - 1)
            evt = threading.Event() if is_last else None
            if is_last:
                last_event = evt
            _text_queue.put((sentence, is_last, evt))

        if last_event is not None:
            last_event.wait()
    else:
        for idx, sentence in enumerate(sentences):
            is_last = (idx == len(sentences) - 1)
            _text_queue.put((sentence, is_last, None))


def shutdown() -> None:
    """Stop the TTS pipeline threads cleanly."""
    _text_queue.put(None)
