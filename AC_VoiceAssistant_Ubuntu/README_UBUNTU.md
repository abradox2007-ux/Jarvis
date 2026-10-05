# Jarvis AI Voice Assistant — Ubuntu Edition 🐧

A fully-featured, autonomous AI voice assistant and smart desktop controller tailored specifically for **Ubuntu Linux** (GNOME Desktop).

---

## 🚀 Quick Start (1-Click Launch)

### Option 1: Double-Click Desktop Icon
1. Copy `Jarvis.desktop` to your Desktop or double-click it inside this folder.
2. If prompted on Ubuntu GNOME, right-click `Jarvis.desktop` and select **"Allow Launching"**.
3. Jarvis will automatically configure everything and launch the voice assistant and web dashboard.

### Option 2: Terminal 1-Click Script
Open your terminal in this folder and run:
```bash
chmod +x start_jarvis.sh
./start_jarvis.sh
```

> **Note**: On the very first run, `start_jarvis.sh` automatically checks and installs any missing system packages (`portaudio19-dev`, `ffmpeg`, `xdotool`, etc.), creates the Python virtual environment (`.venv`), installs all dependencies, and launches Jarvis and your default browser (Firefox) to the live Web Dashboard.

---

## ⚙️ Configuration (`config.json`)

All configuration options are stored in [config.json](file:///config.json).

### Key Settings Pre-Configured for Ubuntu:
- **TTS Engine**: `edge-tts` with high quality natural voice (`en-GB-RyanNeural`)
- **Default Browser**: `firefox`
- **Linux App Aliases**: `firefox`, `gnome-terminal`, `gedit`, `gnome-calculator`, `nautilus`, `code`
- **System Paths**: Linux native home paths (`~/Desktop`, `~/Documents`, `~/Music/My_playlist`)

### Adding AI API Keys (Optional but Recommended)
To enable multi-provider AI chat and intelligent answers:
1. Open `config.json` in any text editor.
2. Insert your API keys in the `api_keys` section:
```json
"api_keys": {
    "groq": "your-groq-api-key-here",
    "gemini": "your-gemini-api-key-here",
    "openai": "your-openai-api-key-here",
    "openrouter": "your-openrouter-api-key-here",
    "perplexity": "your-perplexity-api-key-here"
}
```

---

## 🛠️ Linux Native Integrations

| Feature | Linux Command / Utility |
| :--- | :--- |
| **Volume Control** | `pactl` / `amixer` |
| **Brightness Control** | `brightnessctl` / `xbacklight` |
| **Media Keys (Play/Pause/Next)** | `playerctl` / `xdotool` |
| **Lock Screen** | `loginctl lock-session` / `gnome-screensaver-command -l` |
| **Screenshots** | `scrot` / `gnome-screenshot` / `PIL` |
| **Battery Level** | `/sys/class/power_supply` & `psutil` |
| **Speech Barge-in Interruption** | `sounddevice` + `soundfile` + `pydub` (zero-latency audio cancellation) |
| **App Launcher & File Opener** | `xdg-open` + Linux PATH resolution |

---

## 🗣️ Voice Commands Cheatsheet

- **Wake Word**: Say `"Jarvis"` or `"Hey Jarvis"`.
- **System Control**:
  - *"Volume up"*, *"Volume down"*, *"Mute volume"*, *"Set volume to 50%"*
  - *"Increase brightness"*, *"Dim brightness"*
  - *"Lock the screen"*
  - *"Battery status"*
  - *"Take a screenshot"*
- **Media Control**:
  - *"Play music"*, *"Pause"*, *"Next track"*, *"Resume"*
- **Apps & Web**:
  - *"Open Firefox"*, *"Open terminal"*, *"Open VS Code"*
  - *"Search YouTube for lofi music"*
  - *"Google quantum computing"*
- **Productivity & Notes**:
  - *"Write note: Remember to review pull request"*
  - *"Open quick notes"*
  - *"Dear diary, today was a productive day"*
  - *"Set timer for 10 minutes"*
- **AI & Knowledge**:
  - *"Explain the theory of relativity"*
  - *"Summarize copied text"* (Smart Copy clipboard integration)
  - *"What's the weather in London?"*

---

## 📁 Folder Structure

```
AC_VoiceAssistant_Ubuntu/
├── Jarvis.desktop         # GNOME desktop launcher shortcut
├── start_jarvis.sh        # Universal 1-click startup script (auto-installs venv/packages)
├── setup_ubuntu.sh        # Dedicated system package & pip installer
├── main.py                # Main application entrypoint
├── server.py              # Flask real-time SSE stream & REST API
├── config.json            # Ubuntu configuration & app mappings
├── requirements_ubuntu.txt# Linux Python dependencies
├── frontend/
│   └── index.html         # Premium interactive Web UI Dashboard
├── jarvis/                # Core assistant architecture
│   ├── speech.py          # Linux multi-backend TTS & real-time audio playback
│   ├── router.py          # Intent parser & command router
│   ├── vad.py             # Silero Voice Activity Detection
│   ├── memory.py          # SQLite semantic memory engine
│   ├── plugin_manager.py  # Dynamic plugin engine
│   ├── handlers/          # System, media, apps, AI, notes, timer handlers
│   └── ui/                # Tkinter desktop overlay badge
├── plugins/               # Custom modular plugins (e.g. IP lookup)
└── data/                  # Custom commands, notes, diary, and screenshots
```

---

## 🔧 Troubleshooting

- **Microphone Not Detected**: Check your audio input settings in Ubuntu Settings -> Sound -> Input Device. Make sure your user is in the `audio` group (`sudo usermod -aG audio $USER`).
- **Wayland vs X11**: Window switching (`wmctrl`/`xdotool`) works best on standard X11 / Xorg sessions. If on Wayland, system volume, media, TTS, AI, and app launching work out of the box.
- **Audio Output Permissions**: If using PulseAudio or PipeWire, audio plays smoothly via `sounddevice` or `paplay`.
