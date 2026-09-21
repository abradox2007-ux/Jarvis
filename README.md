# 🎙️ Jarvis — Voice Assistant

An intelligent, local-first AI Voice Assistant with real-time wake word detection, Voice Activity Detection (VAD), fast speech-to-text, neural text-to-speech (Edge-TTS / Piper / SAPI5), Gemini AI intelligence, system audio & workstation controls, background timers & reminders, live extensible custom commands with passkey security, and an interactive 3D holographic web dashboard.

---

## ✨ Features

- **Wake Word & Full-Duplex VAD**: Hands-free activation powered by [openWakeWord](https://github.com/dscripka/openWakeWord) and Silero VAD with **real-time barge-in interruption** (interrupt Jarvis mid-speech).
- **Continuous Conversation & Dot Delimiter**: Remains active until you say *"stop"*, and supports instant multi-command execution using verbal *"dot"* separators.
- **Fast & Accurate STT**: Dual-engine speech recognition using `faster-whisper` (CTranslate2 INT8 CPU inference) and cloud Google Speech Recognition.
- **Studio-Quality Neural TTS**: Multiple speech engine options:
  - **Kokoro-82M ONNX** (State-of-the-art studio-grade local neural voice, <100ms TTFB)
  - **Microsoft Edge-TTS** (Ultra natural cloud neural voice)
  - **Piper TTS** (Fast offline neural voice)
  - **pyttsx3 / Windows SAPI5** (Zero-latency OS native speech)
- **AI Intelligence & Offline Fallback**: Integrated with Google Gemini AI (`google-genai`), OpenAI, and local **Ollama** models (Qwen 2.5 / Llama 3.2) for 100% offline intelligence.
- **System, Audio & Workstation Controls**: Voice control for volume adjustment, media play/pause/skip, lock workstation, screenshots, and battery status.
- **Non-blocking Timers & Voice Reminders**: Background countdown timers and voice reminders with natural language time parsing.
- **Live Dynamic Custom Commands**: User-defined shortcuts in `data/custom_commands.txt` with regex **SafetyGuard** security and PIN passkey authorization.
- **Extensible Plugin Engine**: Drop-in Python plugins in `plugins/` for custom integrations (e.g. IP and network tools).
- **Full Local File Management**: Voice & UI commands for creating, writing notes, renaming, copying, and moving files.
- **Voice Diary & CRUD Dashboard**: Record voice journals with instant visual and audio synchronization.
- **Interactive Holographic Dashboard**: Single-page web dashboard on `http://localhost:5050` with real-time state visualizer, smart home virtual devices, file manager, and diary viewer.

---

## 📁 Project Structure

```text
AC_VoiceAssistant/
├── config.example.json      # Template configuration file
├── config.json              # Your private config (API keys, aliases)
├── main.py                  # Main entry point for voice assistant & Web UI
├── server.py                # Flask backend server for web dashboard
├── requirements.txt         # Python dependencies specification
├── setup_piper.py           # Setup script for Piper local neural TTS (optional)
├── setup_phase2.py          # Setup helper for offline models
├── test_jarvis.py           # Automated unit and integration test suite (46 tests)
├── frontend/                # Web Management Dashboard UI
│   └── index.html           # Modern glassmorphism UI with particle visualizer
├── jarvis/                  # Core assistant package
│   ├── listener.py          # Audio capture, wake word, VAD & STT
│   ├── router.py            # Command parsing, Tamil normalization & dispatch
│   ├── speech.py            # Multi-engine TTS speech worker (Edge-TTS, Piper, SAPI5)
│   ├── vad.py               # Silero Voice Activity Detector (ONNX runtime)
│   ├── plugin_manager.py    # Dynamic plugin loader and dispatcher
│   ├── utils.py             # Config loader and logging utilities
│   └── handlers/            # Modular feature handlers
│       ├── ai.py            # Gemini AI handler & structured action dispatcher
│       ├── apps.py          # Application launcher
│       ├── custom_commands.py # Custom commands, SafetyGuard & PIN passkey
│       ├── diary.py         # Voice diary manager
│       ├── files.py         # Local filesystem operations (rename, copy, cut, write)
│       ├── info.py          # Weather, time, and date info
│       ├── system.py        # Windows volume, media, screenshot & screen lock
│       ├── timer.py         # Non-blocking timers and voice reminders
│       └── urls.py          # Web browser launcher & YouTube handler
├── plugins/                 # Extensible external plugins
│   └── ip_plugin.py         # Sample network IP lookup plugin
└── data/                    # Local storage (diary notes, commands, screenshots)
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10 to 3.13** (64-bit recommended)
- Working Microphone & Speakers / Headphones
- (Windows) Visual C++ 2015–2022 Redistributable (x64)

### 2. Clone the Repository
```bash
git clone https://github.com/abradox2007-ux/Jarvis.git
cd Jarvis
```

### 3. Create & Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
*(If script execution is disabled in PowerShell, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first)*

**On Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**On Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note for PyAudio on Windows:** If `pyaudio` compilation fails, install the prebuilt wheel using `pip install pipwin && pipwin install pyaudio`.

### 5. Configuration Setup

Copy `config.example.json` to `config.json`:
```bash
cp config.example.json config.json
```

Edit `config.json` with your custom settings:
```json
{
  "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
  "stt_engine": "whisper",
  "whisper_model": "base",
  "tts_engine": "edge-tts",
  "edge_tts_voice": "en-US-GuyNeural",
  "active_on_startup": true,
  "continuous_conversation": true,
  "follow_up_timeout": 8.0,
  "weather_city": "Chennai",
  "weather_country": "IN",
  "custom_command_passkey": "1312"
}
```

- Get a free Gemini API Key from [Google AI Studio](https://aistudio.google.com/).

---

## 🏃 Running Jarvis

With your virtual environment activated:

```bash
python main.py
```

1. Jarvis initializes audio streams and preloads speech engines.
2. The web interface automatically opens at `http://localhost:5050`.
3. Say `"Hey Jarvis"` (or speak immediately if `active_on_startup` is enabled) and speak your command!

---

## 🗣️ Example Voice Commands

| Category | Example Voice Commands |
| :--- | :--- |
| **Wake Word** | *"Hey Jarvis"*, *"Hello AC"*, *"ஜார்விஸ்"* |
| **Dismissal / Sleep** | *"Stop"*, *"Standby"*, *"Go to sleep"*, *"Thank you"*, *"போதும்"* |
| **Audio & Media** | *"Volume up"*, *"Set volume to 60%"*, *"Mute volume"*, *"Pause music"*, *"Next track"* |
| **OS & Screen** | *"Lock screen"*, *"Take screenshot"*, *"Battery status"* |
| **Timers & Reminders** | *"Set a timer for 10 minutes"*, *"Remind me to call John in 1 hour"*, *"List timers"* |
| **Applications** | *"Open Notepad"*, *"Launch Chrome"*, *"Open Calculator"* |
| **Web & Music** | *"Open YouTube"*, *"Play Believer"*, *"Search Google for Python tutorials"* |
| **File Operations** | *"Create file project_notes"*, *"Write in notes meeting at 5pm"*, *"Rename file notes to old_notes"* |
| **Voice Diary** | *"Diary finished milestone one today"*, *"Read diary"*, *"Manual diary"* |
| **Smart Home** | *"Turn on the light"*, *"Set AC temperature to 22 degrees"*, *"Set fan speed to high"* |
| **Custom Commands** | *"Run test suite passkey 1312"*, *"My shortcut"* |
| **Plugin Queries** | *"What is my local IP address?"*, *"What is my public IP?"* |
| **Tamil Commands** | *"நேரம் என்ன"*, *"கூகுள் திற"*, *"வானிலை என்ன"* |
| **AI Fallback** | *"Explain quantum computing in simple terms"*, *"Write a poem about coding"* |

---

## 🧪 Testing

Run the automated test suite:
```bash
python -m unittest test_jarvis.py -v
```

---

## 📄 License

This project is licensed under the MIT License — see the repository for details.
