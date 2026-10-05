"""jarvis/handlers/system.py — Linux/Windows OS system, volume, brightness, media, and screen controls."""

from __future__ import annotations

import ctypes
import datetime
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Virtual Key Codes for Windows
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


def _send_virtual_key(vk_code: int) -> None:
    """Send a virtual key press and release on Windows."""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        except Exception as e:
            logger.warning("Failed to send virtual key 0x%X: %s", vk_code, e)


def mute_volume() -> str:
    """Toggle mute audio."""
    if sys.platform == "win32":
        _send_virtual_key(VK_VOLUME_MUTE)
    else:
        # Linux PulseAudio / PipeWire / ALSA
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("amixer"):
            subprocess.run(["amixer", "-D", "pulse", "set", "Master", "1+", "toggle"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdotool"):
            subprocess.run(["xdotool", "key", "XF86AudioMute"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Toggled volume mute."


def volume_up(steps: int = 5) -> str:
    """Increase system volume by given steps (each step ~2-5%)."""
    if sys.platform == "win32":
        for _ in range(max(1, min(steps, 25))):
            _send_virtual_key(VK_VOLUME_UP)
    else:
        pct = max(1, min(steps * 2, 50))
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{pct}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("amixer"):
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{pct}%+"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdotool"):
            for _ in range(steps):
                subprocess.run(["xdotool", "key", "XF86AudioRaiseVolume"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Increased volume."


def volume_down(steps: int = 5) -> str:
    """Decrease system volume by given steps (each step ~2-5%)."""
    if sys.platform == "win32":
        for _ in range(max(1, min(steps, 25))):
            _send_virtual_key(VK_VOLUME_DOWN)
    else:
        pct = max(1, min(steps * 2, 50))
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{pct}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("amixer"):
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{pct}%-"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdotool"):
            for _ in range(steps):
                subprocess.run(["xdotool", "key", "XF86AudioLowerVolume"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Decreased volume."


def set_volume_percent(percent: int) -> str:
    """Set volume percentage."""
    percent = max(0, min(100, percent))
    if sys.platform == "win32":
        for _ in range(50):
            _send_virtual_key(VK_VOLUME_DOWN)
        steps_up = percent // 2
        for _ in range(steps_up):
            _send_virtual_key(VK_VOLUME_UP)
    else:
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("amixer"):
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"Set system volume to {percent} percent."


def media_play_pause() -> str:
    """Toggle media play/pause."""
    if sys.platform == "win32":
        _send_virtual_key(VK_MEDIA_PLAY_PAUSE)
    else:
        if shutil.which("playerctl"):
            subprocess.run(["playerctl", "play-pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdotool"):
            subprocess.run(["xdotool", "key", "XF86AudioPlay"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Toggled media playback."


def media_next() -> str:
    """Skip to next media track."""
    if sys.platform == "win32":
        _send_virtual_key(VK_MEDIA_NEXT_TRACK)
    else:
        if shutil.which("playerctl"):
            subprocess.run(["playerctl", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdotool"):
            subprocess.run(["xdotool", "key", "XF86AudioNext"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Playing next track."


def media_previous() -> str:
    """Skip to previous media track."""
    if sys.platform == "win32":
        _send_virtual_key(VK_MEDIA_PREV_TRACK)
    else:
        if shutil.which("playerctl"):
            subprocess.run(["playerctl", "previous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdotool"):
            subprocess.run(["xdotool", "key", "XF86AudioPrev"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Playing previous track."


def media_stop() -> str:
    """Stop media playback."""
    if sys.platform == "win32":
        _send_virtual_key(VK_MEDIA_STOP)
    else:
        if shutil.which("playerctl"):
            subprocess.run(["playerctl", "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdotool"):
            subprocess.run(["xdotool", "key", "XF86AudioStop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Stopped media playback."


def lock_workstation() -> str:
    """Lock the workstation (Linux / Windows)."""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.LockWorkStation()
            return "Locking workstation."
        except Exception:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False)
            return "Locking workstation."
    else:
        # Linux GNOME / systemd lock
        if shutil.which("loginctl"):
            subprocess.run(["loginctl", "lock-session"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdg-screensaver"):
            subprocess.run(["xdg-screensaver", "lock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("gnome-screensaver-command"):
            subprocess.run(["gnome-screensaver-command", "-l"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Locking Ubuntu session."


def set_brightness(percent: int) -> str:
    """Set monitor brightness percentage."""
    percent = max(0, min(100, percent))
    if sys.platform == "win32":
        try:
            cmd = f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {percent})"
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=3)
            return f"Set screen brightness to {percent} percent."
        except Exception as e:
            logger.warning("Failed to set brightness: %s", e)
            return "Could not adjust screen brightness on this display."
    else:
        # Linux brightnessctl / xbacklight
        if shutil.which("brightnessctl"):
            subprocess.run(["brightnessctl", "set", f"{percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Set screen brightness to {percent} percent."
        elif shutil.which("xbacklight"):
            subprocess.run(["xbacklight", "-set", str(percent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Set screen brightness to {percent} percent."
        return "Could not adjust screen brightness. Install brightnessctl."


def take_screenshot(target_dir: str = "./data/screenshots") -> str:
    """Capture full screen and save as PNG image."""
    os.makedirs(target_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(target_dir, f"screenshot_{timestamp}.png")

    # 1. On Linux, try scrot or gnome-screenshot
    if sys.platform != "win32":
        if shutil.which("scrot"):
            try:
                subprocess.run(["scrot", filepath], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "Screenshot saved successfully."
            except Exception:
                pass
        if shutil.which("gnome-screenshot"):
            try:
                subprocess.run(["gnome-screenshot", "-f", filepath], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "Screenshot saved successfully."
            except Exception:
                pass

    # 2. Try PIL ImageGrab
    try:
        from PIL import ImageGrab
        screenshot = ImageGrab.grab(all_screens=True)
        screenshot.save(filepath, "PNG")
        logger.info("Saved PIL screenshot to %s", filepath)
        return "Screenshot saved successfully."
    except Exception as exc:
        logger.warning("Failed to capture screenshot: %s", exc)
        return f"Failed to take screenshot: {exc}"


def get_battery_status() -> str:
    """Retrieve system battery percentage and charging state."""
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery:
            plugged = "plugged in" if battery.power_plugged else "on battery"
            return f"Battery is at {battery.percent:.0f} percent and {plugged}."
    except Exception:
        pass

    # Linux sysfs fallback
    if sys.platform != "win32":
        for b_path in ["/sys/class/power_supply/BAT0", "/sys/class/power_supply/BAT1"]:
            cap_file = os.path.join(b_path, "capacity")
            if os.path.exists(cap_file):
                try:
                    with open(cap_file, "r") as f:
                        cap = f.read().strip()
                    status_file = os.path.join(b_path, "status")
                    stat = "Discharging"
                    if os.path.exists(status_file):
                        with open(status_file, "r") as f:
                            stat = f.read().strip()
                    return f"Battery is at {cap} percent and {stat}."
                except Exception:
                    pass

    return "Battery information is not available."


def terminate_jarvis(delay_seconds: float = 1.2) -> str:
    """
    Completely terminate Jarvis cleanly.
    """
    import threading
    import time

    def _shutdown_worker() -> None:
        time.sleep(delay_seconds)
        try:
            from server import set_status
            set_status("idle", "Jarvis is offline.")
        except Exception:
            pass
        try:
            from jarvis.speech import shutdown as shutdown_speech
            shutdown_speech()
        except Exception:
            pass

        os._exit(0)

    threading.Thread(target=_shutdown_worker, daemon=False).start()
    return "Terminating Jarvis and closing session. Goodbye."
