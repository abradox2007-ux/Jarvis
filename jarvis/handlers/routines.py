"""jarvis/handlers/routines.py — Daily routines (Good Morning, Good Night, Daily Briefing)."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from jarvis.handlers import info, media, system

logger = logging.getLogger(__name__)


def run_morning_routine(config: dict[str, Any], play_music: bool = False) -> str:
    """
    Execute a comprehensive morning routine:
    1. Greets the user with title/name.
    2. Reads current time & date.
    3. Fetches live weather for the configured city.
    4. Reports battery / power status.
    5. Checks for today's diary notes or active timers.
    6. Optionally starts morning playlist playback.
    """
    title = config.get("user_title", "Sir")
    city = config.get("weather_city", "Chennai")
    country = config.get("weather_country", "IN")
    now = datetime.datetime.now()

    parts = []

    # Greeting & Time
    time_str = now.strftime("%I:%M %p")
    date_str = now.strftime("%A, %B %d, %Y")
    parts.append(f"Good morning, {title}. It is {time_str} on {date_str}.")

    # Weather
    if config.get("morning_routine_include_weather", True):
        try:
            weather_text = info.tell_weather(city, country)
            if weather_text and not weather_text.lower().startswith("couldn't"):
                parts.append(weather_text)
        except Exception as e:
            logger.debug("Morning weather error: %s", e)

    # Battery
    if config.get("morning_routine_include_battery", True):
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery:
                plugged_str = "plugged in" if battery.power_plugged else "on battery power"
                parts.append(f"Power levels are at {battery.percent}%, {plugged_str}.")
        except Exception:
            pass

    # Diary notes for today
    try:
        from jarvis.handlers.diary import DIARY_PATH
        if DIARY_PATH.exists():
            content = DIARY_PATH.read_text(encoding="utf-8", errors="ignore").strip()
            today_key = now.strftime("%Y-%m-%d")
            if today_key in content:
                parts.append("You have existing notes recorded in your diary for today.")
    except Exception:
        pass

    # Music Playback
    should_play_music = play_music or config.get("morning_routine_play_music", False)
    if should_play_music:
        playlist_dir = config.get("local_playlist_dir", r"C:\Users\Abinesh\Music\My_playlist")
        try:
            media_msg = media.play_local_playlist(playlist_dir, shuffle=True)
            parts.append(f"Starting your morning playlist. {media_msg}")
        except Exception as e:
            logger.warning("Failed to start morning music: %s", e)

    parts.append("All systems operational. How may I assist you today?")
    return " ".join(parts)


def run_night_routine(config: dict[str, Any]) -> str:
    """
    Execute a soothing night / sleep routine:
    1. Sets volume to a relaxed level (e.g. 15%).
    2. Adjusts brightness if supported.
    3. Bids user a peaceful good night.
    """
    title = config.get("user_title", "Sir")
    night_volume = int(config.get("night_routine_set_volume", 15))
    night_brightness = int(config.get("night_routine_set_brightness", 20))

    actions_taken = []

    # Adjust Volume
    try:
        system.set_volume_percent(night_volume)
        actions_taken.append(f"volume reduced to {night_volume}%")
    except Exception as e:
        logger.debug("Failed setting night volume: %s", e)

    # Adjust Brightness
    try:
        system.set_brightness(night_brightness)
        actions_taken.append(f"screen brightness set to {night_brightness}%")
    except Exception as e:
        logger.debug("Brightness adjustment skipped: %s", e)

    action_summary = f" I have {', and '.join(actions_taken)}." if actions_taken else ""
    return f"Good night, {title}.{action_summary} Systems are going into quiet standby mode. Sleep well."
