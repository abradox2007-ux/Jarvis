"""jarvis/listener.py — Microphone listener with dual-engine wake word detection, Silero VAD, and Whisper/Google STT."""

from __future__ import annotations

import logging
import re
import queue
import threading
import time
import collections
from typing import Callable, Optional
import numpy as np
import speech_recognition as sr

from jarvis.vad import SileroVAD
from jarvis.utils import load_config
from jarvis.speech import is_speaking

logger = logging.getLogger(__name__)

WAKE_WORDS = [
    "hey jarvis", "hey, jarvis", "hey,jarvis", "jarvis",
    "hello jarvis", "hi jarvis", "ok jarvis", "okay jarvis",
    "hey ac", "hey, ac", "hey,ac", "hello ac",
    "alexa", "ஜார்விஸ்", "ஹே ஜார்விஸ்"
]

PHONETIC_JARVIS = {
    "jarvis", "jervis", "jarvus", "javis", "jarves", "charvis",
    "travis", "service", "harvest", "starfish", "artist"
}


class AudioNoiseFilter:
    """
    Real-time streaming audio pre-filter for microphone input.
    - Bandpass filter (50 Hz - 7500 Hz) to eliminate DC offset, AC/fan rumble, and electrical hiss.
    """
    def __init__(self, sample_rate: int = 16000, low_cutoff: float = 50.0, high_cutoff: float = 7500.0) -> None:
        self.sample_rate = sample_rate
        self._has_scipy = False
        self._sos = None
        self._zi = None

        try:
            import scipy.signal as signal
            self._sos = signal.butter(2, [low_cutoff, high_cutoff], btype='bandpass', fs=sample_rate, output='sos')
            self._zi = signal.sosfilt_zi(self._sos)
            self._has_scipy = True
        except Exception as e:
            logger.debug("scipy not available for SOS bandpass filter: %s", e)

    def process_frame(self, raw_bytes: bytes) -> bytes:
        """Process 16-bit PCM mono audio chunk and return cleaned audio bytes."""
        if not raw_bytes:
            return raw_bytes

        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) == 0:
            return raw_bytes

        # Bandpass filter to remove DC offset and low rumble
        if self._has_scipy and self._sos is not None:
            try:
                import scipy.signal as signal
                samples, self._zi = signal.sosfilt(self._sos, samples, zi=self._zi)
            except Exception:
                pass

        cleaned_samples = np.clip(samples, -32768, 32767).astype(np.int16)
        return cleaned_samples.tobytes()


class Listener:
    def __init__(
        self,
        device_index: int | None = None,
        stt_engine: str = "google",
        whisper_model: str = "base",
        on_network_error: Callable[[], None] | None = None,
        on_mic_error: Callable[[], None] | None = None,
    ) -> None:
        self._recognizer = sr.Recognizer()
        self._recognizer.pause_threshold = 0.7
        self._recognizer.dynamic_energy_threshold = True
        self._ambient_adjusted = False
        self._device_index = device_index
        self._stt_engine = stt_engine.lower()
        self._whisper_model = whisper_model
        self._on_network_error = on_network_error or (lambda: None)
        self._on_mic_error = on_mic_error or (lambda: None)

        self._whisper_model_instance = None
        self._openwakeword_model = None
        self._vad = None

        # Load config
        try:
            config = load_config()
        except Exception:
            config = {}

        self._wake_word_engine = config.get("wake_word_engine", "openwakeword")
        self._wake_word_model_name = config.get("wake_word_model", "hey_jarvis")
        self._wake_word_threshold = config.get("wake_word_threshold", 0.38)
        self._vad_threshold = config.get("vad_threshold", 0.15)
        self._vad_initial_timeout = config.get("vad_initial_timeout", 7.0)
        self._vad_model_path = config.get("vad_model_path", "bin/vad/silero_vad.onnx")

        # 1. Preload STT Whisper
        if self._stt_engine == "whisper":
            logger.info("Preloading faster-whisper model '%s'...", self._whisper_model)
            try:
                from faster_whisper import WhisperModel
                self._whisper_model_instance = WhisperModel(
                    self._whisper_model,
                    device="cpu",
                    compute_type="int8"
                )
                logger.info("faster-whisper model preloaded.")
            except Exception as e:
                logger.warning("Failed to preload faster-whisper: %s. Will fallback to Google STT.", e)
                self._whisper_model_instance = None

        # 2. Initialize openWakeWord
        if self._wake_word_engine == "openwakeword":
            logger.info("Initializing openWakeWord with model '%s'...", self._wake_word_model_name)
            try:
                from openwakeword.model import Model
                self._openwakeword_model = Model(
                    wakeword_models=[self._wake_word_model_name],
                    inference_framework="onnx"
                )
                logger.info("openWakeWord initialized.")
            except Exception as e:
                logger.error("Failed to load openWakeWord: %s", e)

        # 3. Initialize Silero VAD
        logger.info("Initializing Silero VAD from '%s'...", self._vad_model_path)
        try:
            self._vad = SileroVAD(self._vad_model_path)
            logger.info("Silero VAD initialized.")
        except Exception as e:
            logger.error("Failed to load Silero VAD: %s", e)

        # 4. Start background always-on microphone streaming thread
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        self._running = True
        self._mic_thread = threading.Thread(target=self._mic_worker, daemon=True)
        self._mic_thread.start()

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def contains_wake_word(text: str) -> bool:
        """Return True if *text* contains any wake-word variant or phonetic approximation."""
        if not text:
            return False
        t = text.lower().strip()
        for ww in WAKE_WORDS:
            if ww in t:
                return True

        # Fuzzy word checks
        clean_words = re.findall(r"\b\w+\b", t)
        for i, word in enumerate(clean_words):
            # Phonetic match for Jarvis
            if word in PHONETIC_JARVIS:
                return True
            # Greeting + word ("hey/hi/hello/ok" + word)
            if word in ("hey", "hay", "hi", "hello", "ok", "okay") and i + 1 < len(clean_words):
                nxt = clean_words[i + 1]
                if nxt in PHONETIC_JARVIS or nxt in ("ac", "a", "c"):
                    return True
        return False

    @staticmethod
    def extract_command_from_wake(text: str) -> str:
        """Strip the wake word prefix and return the remainder."""
        if not text:
            return ""
        t = text.strip()
        lower_t = t.lower()
        for ww in WAKE_WORDS:
            if ww in lower_t:
                idx = lower_t.index(ww) + len(ww)
                remainder = t[idx:].lstrip(",:.- ").strip()
                if remainder:
                    return remainder

        # Fuzzy strip
        tokens = re.split(r"\s+", t)
        for i, tok in enumerate(tokens):
            clean = tok.lower().rstrip(",:.-")
            if clean in ("hey", "hay", "hi", "hello", "ok", "okay") and i + 1 < len(tokens):
                nxt = tokens[i + 1].lower().rstrip(",:.-")
                if nxt in PHONETIC_JARVIS or nxt in ("ac", "a.c"):
                    return " ".join(tokens[i + 2:]).strip()
            elif clean in PHONETIC_JARVIS:
                return " ".join(tokens[i + 1:]).strip()

        return t

    @staticmethod
    def _compute_rms(audio_bytes: bytes) -> float:
        """Compute root mean square (RMS) energy of 16-bit PCM audio."""
        if not audio_bytes:
            return 0.0
        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        if len(samples) == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))

    # ── Streaming Microphone Worker ───────────────────────────────────────────

    def _mic_worker(self) -> None:
        """Background thread that reads raw audio frames from the mic continuously."""
        import pyaudio
        
        p = pyaudio.PyAudio()
        stream = None
        try:
            # We record at 16000Hz, Mono, 16-bit PCM (standard for VAD, wake word, STT)
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=1024
            )
        except Exception as e:
            logger.error("Failed to open PyAudio mic stream: %s", e)
            self._on_mic_error()
            p.terminate()
            return

        noise_filter = AudioNoiseFilter()
        logger.info("Microphone stream opened successfully with clean filter.")
        while self._running:
            try:
                # Read 1024 samples (64ms of audio)
                data = stream.read(1024, exception_on_overflow=False)
                if data:
                    cleaned_data = noise_filter.process_frame(data)
                    # Full-Duplex Barge-in Detection:
                    if is_speaking():
                        # Check if user is speaking over the assistant audio
                        is_barge_in = False
                        if self._vad is not None:
                            chunk = np.frombuffer(cleaned_data, dtype=np.int16).astype(np.float32) / 32768.0
                            prob1 = self._vad.get_speech_probability(chunk[:512])
                            prob2 = self._vad.get_speech_probability(chunk[512:])
                            if (prob1 > 0.75 or prob2 > 0.75) and self._compute_rms(cleaned_data) > 35.0:
                                is_barge_in = True
                        elif self._compute_rms(cleaned_data) > 80.0:
                            is_barge_in = True

                        if is_barge_in:
                            logger.info("Barge-in detected during speech! Stopping playback immediately.")
                            from jarvis.speech import stop_speaking
                            stop_speaking()
                            # Flush stale queue and start capturing user interruption
                            while not self._audio_queue.empty():
                                try:
                                    self._audio_queue.get_nowait()
                                except Exception:
                                    break
                            self._audio_queue.put(cleaned_data)
                    else:
                        self._audio_queue.put(cleaned_data)
            except Exception as e:
                logger.warning("Error reading audio frame: %s", e)
                time.sleep(0.05)

        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        p.terminate()
        logger.info("Microphone stream closed.")

    # ── VAD Capturing State Machine ───────────────────────────────────────────

    def _capture_speech_with_vad(
        self,
        initial_audio: bytes = b"",
        max_duration: float = 12.0
    ) -> sr.AudioData | None:
        """
        Record audio chunks from the queue using Silero VAD + RMS energy until speech ends.
        """
        accumulated_frames = [initial_audio] if initial_audio else []
        
        if self._vad is not None:
            self._vad.reset()
        
        speech_started = False
        silence_start_time = None
        start_time = time.time()

        # Run VAD on initial_audio to see if speech has already started
        if initial_audio and self._vad is not None:
            initial_samples = np.frombuffer(initial_audio, dtype=np.int16).astype(np.float32) / 32768.0
            for i in range(0, len(initial_samples), 512):
                if i + 512 <= len(initial_samples):
                    if self._vad.is_speech(initial_samples[i : i + 512], threshold=self._vad_threshold):
                        speech_started = True

        while self._running:
            try:
                from server import is_standby_requested
                if is_standby_requested():
                    logger.info("Standby requested, aborting active speech capture.")
                    return None
            except Exception:
                pass

            if time.time() - start_time > max_duration:
                logger.debug("Reached max command duration limit (%.1fs).", max_duration)
                break
                
            try:
                data = self._audio_queue.get(timeout=0.4)
            except queue.Empty:
                break
                
            accumulated_frames.append(data)
            
            # Check VAD & RMS on the new chunk
            chunk_rms = self._compute_rms(data)
            is_speech_chunk = False

            if self._vad is not None:
                chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                prob1 = self._vad.get_speech_probability(chunk[:512])
                prob2 = self._vad.get_speech_probability(chunk[512:])
                is_speech_chunk = (prob1 >= self._vad_threshold) or (prob2 >= self._vad_threshold) or (chunk_rms > 25.0)
            else:
                is_speech_chunk = chunk_rms > 20.0

            if is_speech_chunk:
                if not speech_started:
                    logger.info("Speech detected (RMS: %.1f). Recording...", chunk_rms)
                    speech_started = True
                silence_start_time = None
            else:
                if speech_started:
                    if silence_start_time is None:
                        silence_start_time = time.time()
                    elif time.time() - silence_start_time > 0.85:
                        logger.info("Speech ended (pause detected).")
                        break
                else:
                    if time.time() - start_time > self._vad_initial_timeout:
                        logger.info("Initial listening timeout (no speech detected).")
                        break

        total_audio = b"".join(accumulated_frames)
        total_duration = len(total_audio) / (16000 * 2)  # 16kHz, 16-bit mono = 32000 bytes/sec
        total_rms = self._compute_rms(total_audio)

        if total_duration >= 0.25 and (speech_started or total_rms > 15.0):
            return sr.AudioData(total_audio, 16000, 2)

        logger.debug("Captured audio too short or silent (duration: %.2fs, RMS: %.1f).", total_duration, total_rms)
        return None

    def _transcribe(self, audio: sr.AudioData | None) -> str | None:
        """Transcribe audio with primary engine and automatic fallback."""
        if audio is None:
            return None

        # 1. Try Whisper if enabled
        if self._stt_engine == "whisper" and self._whisper_model_instance is not None:
            try:
                import io
                wav_data = io.BytesIO(audio.get_wav_data(convert_rate=16000, convert_width=2))
                segments, info = self._whisper_model_instance.transcribe(
                    wav_data,
                    beam_size=3,
                    condition_on_previous_text=False
                )
                text_segments = []
                for segment in segments:
                    if segment.no_speech_prob < 0.88 and segment.text.strip():
                        text_segments.append(segment.text.strip())
                text = " ".join(text_segments).strip()

                # Filter out standard Whisper hallucinations on silence
                if text:
                    cleaned_text = text.lower().strip().rstrip(".!?")
                    hallucinations = {
                        "thank you", "thank you for watching", "you", 
                        "please subscribe", "subscribe", "bye", "watching",
                        "thank you.", "subtitles by", "translated by", "."
                    }
                    if cleaned_text not in hallucinations:
                        logger.info("Transcribed (Whisper): '%s'", text)
                        return text
                    else:
                        logger.debug("Filtered Whisper hallucination: '%s'", text)
            except Exception as exc:
                logger.warning("Whisper transcription failed: %s. Trying Google STT...", exc)

        # 2. Try Google Speech Recognition (default or fallback)
        try:
            text = self._recognizer.recognize_google(audio, language="en-IN")
            if text and text.strip():
                logger.info("Transcribed (Google en-IN): '%s'", text)
                return text.strip()
        except sr.UnknownValueError:
            try:
                text = self._recognizer.recognize_google(audio, language="en-US")
                if text and text.strip():
                    logger.info("Transcribed (Google en-US): '%s'", text)
                    return text.strip()
            except sr.UnknownValueError:
                pass
            except sr.RequestError:
                self._on_network_error()
                return None
        except sr.RequestError:
            self._on_network_error()
            return None

        # 3. If Whisper was not primary but Google failed, try Whisper as fallback
        if self._whisper_model_instance is not None and self._stt_engine != "whisper":
            try:
                import io
                wav_data = io.BytesIO(audio.get_wav_data(convert_rate=16000, convert_width=2))
                segments, info = self._whisper_model_instance.transcribe(wav_data, beam_size=3)
                text = " ".join([s.text.strip() for s in segments if s.text.strip()]).strip()
                if text:
                    logger.info("Transcribed (Whisper fallback): '%s'", text)
                    return text
            except Exception:
                pass

        logger.info("Speech could not be recognized.")
        return None

    # ── Public interface ──────────────────────────────────────────────────────

    def wait_for_wake_word(self) -> tuple[str, Optional[str]]:
        """
        Block until the wake word is detected via openWakeWord or acoustic STT spotter.
        Returns (full_transcript, inline_command_or_None).
        """
        time.sleep(0.2)

        # Clear queue of stale audio
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        if self._vad is not None:
            self._vad.reset()

        # Rolling history buffer (1.5 seconds) to catch inline commands
        history_buffer = collections.deque(maxlen=24)
        wakeword_accumulator = np.array([], dtype=np.int16)

        # Speech spotting accumulator for acoustic fallback
        spotter_frames = []
        spotter_speech_count = 0

        logger.info("Waiting for wake word 'Hey Jarvis' (threshold=%.2f)...", self._wake_word_threshold)

        while self._running:
            try:
                data = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            history_buffer.append(data)
            chunk_energy = self._compute_rms(data)

            # ── 1. Fast Path: openWakeWord ONNX Inference ──────────────────────
            if self._openwakeword_model is not None:
                chunk = np.frombuffer(data, dtype=np.int16)
                wakeword_accumulator = np.concatenate([wakeword_accumulator, chunk])

                while len(wakeword_accumulator) >= 1280:
                    predict_chunk = wakeword_accumulator[:1280]
                    wakeword_accumulator = wakeword_accumulator[1280:]

                    predictions = self._openwakeword_model.predict(predict_chunk)
                    score = predictions.get(self._wake_word_model_name, 0.0)

                    if score >= self._wake_word_threshold:
                        logger.info(
                            "Wake word '%s' confirmed via openWakeWord! Score: %.2f (energy: %.1f)",
                            self._wake_word_model_name, score, chunk_energy
                        )
                        wakeword_accumulator = np.array([], dtype=np.int16)
                        try:
                            self._openwakeword_model.reset()
                        except Exception:
                            pass

                        # Collect history audio + short lookahead to catch any inline command
                        pre_trigger_audio = b"".join(list(history_buffer))
                        speech_detected = False
                        check_chunks = []
                        for _ in range(8):  # 8 chunks of 64ms = ~512ms
                            try:
                                chk = self._audio_queue.get(timeout=0.4)
                                check_chunks.append(chk)
                                if self._vad is not None:
                                    f_chk = np.frombuffer(chk, dtype=np.int16).astype(np.float32) / 32768.0
                                    if (self._vad.get_speech_probability(f_chk[:512]) >= self._vad_threshold) or (self._compute_rms(chk) > 50.0):
                                        speech_detected = True
                            except queue.Empty:
                                break

                        if speech_detected:
                            logger.info("Inline command detected (speech continued).")
                            audio_data = self._capture_speech_with_vad(
                                pre_trigger_audio + b"".join(check_chunks)
                            )
                            text = self._transcribe(audio_data)
                            if text:
                                cmd = self.extract_command_from_wake(text)
                                return text, cmd if cmd else None
                        return "", None

            # ── 2. Acoustic Spotter Path (Acoustic STT Fallback) ───────────────
            is_speech = False
            if self._vad is not None:
                f_chk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                is_speech = (self._vad.get_speech_probability(f_chk[:512]) >= self._vad_threshold) or (chunk_energy > 60.0)
            else:
                is_speech = chunk_energy > 55.0

            if is_speech:
                spotter_frames.append(data)
                spotter_speech_count += 1
            else:
                if spotter_speech_count > 0:
                    spotter_frames.append(data)

            # When speech ends or buffer reaches ~1.8s of voice, check transcription
            if (spotter_speech_count >= 8 and (not is_speech or len(spotter_frames) >= 28)) or (len(spotter_frames) >= 36):
                spotter_audio_bytes = b"".join(spotter_frames)
                spotter_frames = []
                spotter_speech_count = 0

                if len(spotter_audio_bytes) >= 16000:  # >= 0.5s of audio
                    audio_obj = sr.AudioData(spotter_audio_bytes, 16000, 2)
                    text = self._transcribe(audio_obj)
                    if text and self.contains_wake_word(text):
                        logger.info("Wake word confirmed via Acoustic Spotter: '%s'", text)
                        cmd = self.extract_command_from_wake(text)
                        return text, cmd if cmd else None

    def capture_command(
        self,
        inline_command: str | None = None,
        timeout: int = 15,
    ) -> str | None:
        """
        Capture and return one spoken command (or return *inline_command* immediately).
        Returns None if nothing is heard.
        """
        if inline_command:
            return inline_command

        # Settle audio queue
        time.sleep(0.1)
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        logger.info("Listening for command...")
        audio = self._capture_speech_with_vad(b"", max_duration=float(timeout))
        return self._transcribe(audio)

    def close(self) -> None:
        """Stop the background mic streaming thread cleanly."""
        self._running = False
        if self._mic_thread.is_alive():
            self._mic_thread.join(timeout=2.0)
