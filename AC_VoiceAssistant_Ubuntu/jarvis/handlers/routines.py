"""jarvis/handlers/routines.py — Daily routines (Good Morning, Good Night, Daily Briefing)."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from jarvis.handlers import info, media, system

logger = logging.getLogger(__name__)


import difflib
import os
import re
import subprocess
import threading
from pathlib import Path


def find_best_project_directory(
    project_query: str | None, search_dirs: list[str]
) -> tuple[Path | None, str | None]:
    """
    Search for project folders in search_dirs.
    If project_query is given, fuzzy match against folder names and sort by recency.
    If project_query is None or empty, return the most recently modified project directory.
    Returns (project_path, project_display_name).
    """
    candidate_folders: list[Path] = []

    for raw_dir in search_dirs:
        try:
            base_dir = Path(raw_dir).expanduser()
            if not base_dir.exists() or not base_dir.is_dir():
                continue
            for item in base_dir.iterdir():
                try:
                    if item.is_dir() and not item.name.startswith((".", "$")):
                        candidate_folders.append(item)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Error scanning directory %s: %s", raw_dir, e)

    if not candidate_folders:
        return None, None

    if not project_query or not project_query.strip():
        try:
            candidate_folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            best = candidate_folders[0]
            return best, best.name
        except Exception:
            return candidate_folders[0], candidate_folders[0].name

    query = project_query.strip().lower()

    for folder in candidate_folders:
        if folder.name.lower() == query:
            return folder, folder.name

    sub_matches = [
        f for f in candidate_folders if query in f.name.lower() or f.name.lower() in query
    ]
    if sub_matches:
        sub_matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return sub_matches[0], sub_matches[0].name

    folder_names = [f.name for f in candidate_folders]
    matches = difflib.get_close_matches(project_query, folder_names, n=3, cutoff=0.35)
    if matches:
        matched_folders = [f for f in candidate_folders if f.name in matches]
        matched_folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return matched_folders[0], matched_folders[0].name

    candidate_folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidate_folders[0], candidate_folders[0].name


def get_today_schedule_summary() -> str:
    """Read today's schedule/notes and return a friendly spoken summary."""
    now_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    schedule_items = []

    # 1. Check quick notes
    try:
        from jarvis.handlers.notes import NOTES_PATH

        if NOTES_PATH.exists():
            with open(NOTES_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line_clean = line.strip()
                    if line_clean.startswith("- [") and f"[{now_date_str}" in line_clean:
                        m = re.match(r"^-\s*\[.*?\]\s*(?:\(.*?\):)?\s*(.*)$", line_clean)
                        if m:
                            schedule_items.append(m.group(1).strip())
                        else:
                            schedule_items.append(line_clean.lstrip("- "))
    except Exception:
        pass

    # 2. Check Diary
    try:
        from jarvis.handlers.diary import DIARY_PATH

        if DIARY_PATH.exists():
            content = DIARY_PATH.read_text(encoding="utf-8", errors="ignore").strip()
            if now_date_str in content:
                schedule_items.append("You have notes recorded in your personal diary.")
    except Exception:
        pass

    if schedule_items:
        items_text = ", ".join(schedule_items[:3])
        return f"Regarding your schedule for today, you have: {items_text}."
    else:
        return "Your schedule is clear for today."


def run_morning_routine(
    config: dict[str, Any],
    play_music: bool = False,
    project_query: str | None = None,
    greeting_override: str | None = None,
) -> str:
    """
    Execute a comprehensive 7-step morning / work mode routine:
    1. Wish the user (Salutation).
    2. Tell Time, Date, Day, Weather (maintained in this exact sequence).
    3. Update on schedule / agenda for today.
    4. Set brightness to 80% (or configured level).
    5. Open Antigravity IDE & project folder.
    6. Play playlist.
    """
    title = config.get("user_title", "Sir")
    city = config.get("weather_city", "Chennai")
    country = config.get("weather_country", "IN")
    now = datetime.datetime.now()

    parts = []

    # 1. Wish / Salutation (Time-aware or overridden)
    if greeting_override:
        greeting = greeting_override
    else:
        hour = now.hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
    parts.append(f"{greeting}, {title}.")

    # 2. Time, Date, Day, Weather (Strict Sequence)
    time_str = now.strftime("%I:%M %p")
    date_str = now.strftime("%B %d, %Y")
    day_str = now.strftime("%A")
    parts.append(f"The time is {time_str} on {date_str}, {day_str}.")

    if config.get("morning_routine_include_weather", True):
        try:
            weather_text = info.tell_weather(city, country)
            if weather_text and not weather_text.lower().startswith("couldn't"):
                parts.append(weather_text)
        except Exception as e:
            logger.debug("Morning weather error: %s", e)

    # 3. Schedule Update
    try:
        schedule_text = get_today_schedule_summary()
        parts.append(schedule_text)
    except Exception as e:
        logger.debug("Schedule summary error: %s", e)

    # 4. Set Brightness to 80
    brightness_level = int(config.get("morning_routine_set_brightness", 80))
    try:
        system.set_brightness(brightness_level)
    except Exception as e:
        logger.debug("Failed setting morning brightness: %s", e)

    # 5 & 6. Open Antigravity IDE & Project Folder
    search_dirs = config.get(
        "project_search_dirs",
        [
            r"~/Desktop",
            r"~/Documents",
        ],
    )
    should_open_ide = config.get("morning_routine_open_antigravity", True)

    app_aliases = config.get("app_aliases", {})
    antigravity_cmd = app_aliases.get(
        "antigravity",
        "antigravity",
    )
    clean_antigravity_exe = antigravity_cmd.strip('"')

    proj_path, proj_name = find_best_project_directory(project_query, search_dirs)

    if should_open_ide:
        try:
            if proj_path and proj_path.exists():
                cmd = f'"{clean_antigravity_exe}" "{str(proj_path)}"'
                subprocess.Popen(cmd, shell=True)
                parts.append(
                    f"Setting brightness to {brightness_level} percent, opening Antigravity IDE with project {proj_name},"
                )
            else:
                cmd = f'"{clean_antigravity_exe}"'
                subprocess.Popen(cmd, shell=True)
                parts.append(
                    f"Setting brightness to {brightness_level} percent, opening Antigravity IDE,"
                )
        except Exception as e:
            logger.warning("Failed to launch Antigravity IDE/Project: %s", e)
            parts.append(f"Setting brightness to {brightness_level} percent,")
    else:
        parts.append(f"Setting brightness to {brightness_level} percent,")

    # 7. Play Playlist / Song (After Antigravity launch)
    should_play_music = play_music or config.get("morning_routine_play_music", True)
    if should_play_music:
        playlist_dir = config.get("local_playlist_dir", r"~/Music/My_playlist")
        try:
            threading.Thread(
                target=media.play_local_playlist,
                args=(playlist_dir, True),
                daemon=True,
            ).start()
            parts.append("and starting your playlist.")
        except Exception as e:
            logger.warning("Failed to start morning music: %s", e)
            parts.append("and preparing your workspace.")
    else:
        parts.append("and preparing your workspace.")

    parts.append("All systems operational. Have a productive day ahead!")
    return " ".join(parts)


run_work_mode = run_morning_routine


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


def run_care_mode(config: dict[str, Any], reason: str = "") -> str:
    """
    Execute proactive Care / Wellness Mode (when user is sick, has a headache, or feels unwell):
    1. Sets system volume to low soothing level (e.g. 15%).
    2. Dims screen brightness to 20-25% to minimize eye strain.
    3. Turns off simulated bright lights / adjusts room environment.
    4. Optionally logs a wellness timestamp to diary.
    5. Returns an empathetic, proactive J.A.R.V.I.S. response.
    """
    title = config.get("user_title", "Sir")
    care_volume = int(config.get("care_mode_volume", 15))
    care_brightness = int(config.get("care_mode_brightness", 25))

    # 1. Lower Volume
    try:
        system.set_volume_percent(care_volume)
    except Exception as e:
        logger.debug("Failed setting care mode volume: %s", e)

    # 2. Dim Screen
    try:
        system.set_brightness(care_brightness)
    except Exception as e:
        logger.debug("Failed setting care mode brightness: %s", e)

    # 3. Smart home adjust (turn off main lights)
    try:
        from server import set_device_state
        set_device_state("light", "off")
    except Exception:
        pass

    # 4. Log health timestamp in diary
    try:
        from jarvis.handlers import diary
        timestamp_note = f"Health check-in: Feeling unwell ({reason if reason else 'unspecified condition'}). Activated Care Mode."
        diary.append_diary_entry(timestamp_note)
    except Exception:
        pass

    prompt_details = f" I have reduced audio volume to {care_volume}%, dimmed your display, and turned off the overhead lighting."
    offer = "Would you like me to notify your emergency contact, postpone your upcoming schedules, or set a rest timer?"
    return f"I'm sorry to hear you're feeling unwell, {title}.{prompt_details} {offer}"


def run_gym_routine(config: dict[str, Any]) -> str:
    """
    Execute Gym / Leaving routine:
    1. Locks PC / workstation.
    2. Turns off simulated lights & AC.
    3. Returns encouraging workout confirmation.
    """
    title = config.get("user_title", "Sir")

    # Smart Home off
    try:
        from server import set_device_state
        set_device_state("light", "off")
        set_device_state("ac", "off")
    except Exception:
        pass

    # Lock screen
    try:
        system.lock_workstation()
    except Exception:
        pass

    return f"All appliances powered down and workstation secured, {title}. Have a great workout at the gym!"


def run_relax_routine(config: dict[str, Any]) -> str:
    """
    Execute Relax / Chill routine:
    1. Sets volume to 40%.
    2. Dims brightness to 40%.
    3. Starts local chill/lofi playlist.
    """
    title = config.get("user_title", "Sir")
    try:
        system.set_volume_percent(40)
        system.set_brightness(40)
    except Exception:
        pass

    playlist_dir = config.get("local_playlist_dir", r"C:\Users\Abinesh\Music\My_playlist")
    try:
        media.play_local_playlist(playlist_dir, shuffle=True)
    except Exception:
        pass

    return f"Relaxation mode initiated, {title}. Lights dimmed and ambient music playing. Take it easy."

