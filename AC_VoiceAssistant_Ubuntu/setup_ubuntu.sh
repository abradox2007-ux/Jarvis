#!/usr/bin/env bash
# ==============================================================================
# Jarvis Voice Assistant — Ubuntu System & Python Dependencies Setup
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "      Jarvis Voice Assistant — Ubuntu Setup Installer   "
echo "========================================================"

echo "[1/4] Updating package repository and installing system packages..."
sudo apt update
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    portaudio19-dev \
    libasound2-dev \
    espeak-ng \
    ffmpeg \
    xdotool \
    playerctl \
    brightnessctl \
    scrot \
    pulseaudio-utils \
    alsa-utils \
    xclip

echo "[2/4] Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "[3/4] Installing Python requirements..."
pip install --upgrade pip
pip install -r requirements_ubuntu.txt

echo "[4/4] Making launcher scripts executable..."
chmod +x start_jarvis.sh
chmod +x setup_ubuntu.sh

echo "========================================================"
echo " Setup complete! You can now start Jarvis anytime by running:"
echo "   ./start_jarvis.sh"
echo "========================================================"
