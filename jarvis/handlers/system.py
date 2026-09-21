"""jarvis/handlers/system.py — Windows OS system, volume, brightness, media, and screen controls."""

from __future__ import annotations

import ctypes
import datetime
import logging
import os
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
    else:
        logger.info("Virtual key simulation only natively supported on Windows.")


def mute_volume() -> str:
    """Toggle mute audio."""
    _send_virtual_key(VK_VOLUME_MUTE)
    return "Toggled volume mute."


def volume_up(steps: int = 5) -> str:
    """Increase system volume by given steps (each step ~2%)."""
    for _ in range(max(1, min(steps, 25))):
        _send_virtual_key(VK_VOLUME_UP)
    return f"Increased volume."


def volume_down(steps: int = 5) -> str:
    """Decrease system volume by given steps (each step ~2%)."""
    for _ in range(max(1, min(steps, 25))):
        _send_virtual_key(VK_VOLUME_DOWN)
    return f"Decreased volume."


def set_volume_percent(percent: int) -> str:
    """Set volume approximately by dropping to 0 and stepping up."""
    percent = max(0, min(100, percent))
    # Step down 50 times to guarantee 0%
    for _ in range(50):
        _send_virtual_key(VK_VOLUME_DOWN)
    # Step up (each step is 2%)
    steps_up = percent // 2
    for _ in range(steps_up):
        _send_virtual_key(VK_VOLUME_UP)
    return f"Set system volume to approximately {percent} percent."


def media_play_pause() -> str:
    """Toggle media play/pause."""
    _send_virtual_key(VK_MEDIA_PLAY_PAUSE)
    return "Toggled media playback."


def media_next() -> str:
    """Skip to next media track."""
    _send_virtual_key(VK_MEDIA_NEXT_TRACK)
    return "Playing next track."


def media_previous() -> str:
    """Skip to previous media track."""
    _send_virtual_key(VK_MEDIA_PREV_TRACK)
    return "Playing previous track."


def media_stop() -> str:
    """Stop media playback."""
    _send_virtual_key(VK_MEDIA_STOP)
    return "Stopped media playback."


def lock_workstation() -> str:
    """Lock the Windows PC."""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.LockWorkStation()
            return "Locking workstation."
        except Exception as e:
            logger.warning("LockWorkStation failed: %s", e)
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False)
            return "Locking workstation."
    return "Locking workstation is only supported on Windows."


def set_brightness(percent: int) -> str:
    """Set monitor brightness percentage on Windows."""
    percent = max(0, min(100, percent))
    if sys.platform == "win32":
        try:
            cmd = f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {percent})"
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=3)
            return f"Set screen brightness to {percent} percent."
        except Exception as e:
            logger.warning("Failed to set brightness: %s", e)
            return "Could not adjust screen brightness on this display."
    return "Brightness control is only supported on Windows."


def take_screenshot(target_dir: str = "./data/screenshots") -> str:
    """Capture full screen and save as PNG image."""
    try:
        from PIL import ImageGrab
        os.makedirs(target_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(target_dir, f"screenshot_{timestamp}.png")
        
        screenshot = ImageGrab.grab()
        screenshot.save(filepath, "PNG")
        logger.info("Saved screenshot to %s", filepath)
        return f"Screenshot saved successfully."
    except Exception as e:
        logger.warning("Failed to capture screenshot: %s", e)
        return f"Failed to take screenshot: {e}"


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

    if sys.platform == "win32":
        try:
            cmd = "Get-CimInstance -ClassName Win32_Battery | Select-Object -ExpandProperty EstimatedChargeRemaining"
            proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=3)
            val = proc.stdout.strip()
            if val and val.isdigit():
                return f"Battery is at {val} percent."
        except Exception as e:
            logger.debug("PowerShell battery query failed: %s", e)

    return "Battery information is not available."
