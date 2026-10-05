#!/usr/bin/env bash
# ==============================================================================
# Jarvis Voice Assistant — Universal Ubuntu Launcher
# Run this script to start Jarvis. On first run, it will automatically
# setup the Python virtual environment and install all dependencies.
# ==============================================================================

set -e

# Change directory to the folder containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "          Starting Jarvis Voice Assistant (Ubuntu)      "
echo "========================================================"

# 1. Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "[!] Python 3 is not installed."
    echo "[*] Installing python3, python3-pip, and python3-venv..."
    sudo apt update && sudo apt install -y python3 python3-pip python3-venv
fi

# 2. Check essential Ubuntu system libraries for audio & automation
MISSING_PKGS=""
for pkg in portaudio19-dev libasound2-dev espeak-ng ffmpeg xdotool playerctl brightnessctl scrot pulseaudio-utils alsa-utils xclip; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING_PKGS="$MISSING_PKGS $pkg"
    fi
done

if [ -n "$MISSING_PKGS" ]; then
    echo "[*] Installing required system libraries for audio and system control:$MISSING_PKGS"
    sudo apt update && sudo apt install -y $MISSING_PKGS || {
        echo "[!] Note: Could not install some system packages with sudo. Continuing with available tools..."
    }
fi

# 3. Create Python Virtual Environment if it does not exist
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating Python virtual environment in .venv..."
    python3 -m venv "$VENV_DIR"
    
    echo "[*] Upgrading pip..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    
    echo "[*] Installing Jarvis Python dependencies from requirements_ubuntu.txt..."
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements_ubuntu.txt"
    echo "[✓] Environment setup complete!"
fi

# 4. Activate venv
source "$VENV_DIR/bin/activate"

# 5. Create necessary directories if missing
mkdir -p "$SCRIPT_DIR/data" "$SCRIPT_DIR/logs" "$SCRIPT_DIR/data/screenshots" "$SCRIPT_DIR/plugins"

# 6. Launch Jarvis
echo "[*] Launching Jarvis Voice Assistant..."
python3 "$SCRIPT_DIR/main.py"
