"""jarvis/handlers/workspace.py — Workspace presets and Focus/Pomodoro session launcher."""

from __future__ import annotations

import logging
from typing import Any

from jarvis.handlers import apps, media, system, timer, urls

logger = logging.getLogger(__name__)


def launch_workspace(profile_name: str, config: dict[str, Any]) -> str:
    """
    Launch a predefined workspace profile (apps, URLs, and optional playlist).
    """
    workspaces = config.get("workspaces", {})
    key = profile_name.strip().lower()

    profile = workspaces.get(key)
    if not profile:
        # Check partial match
        for name, data in workspaces.items():
            if key in name or name in key:
                profile = data
                profile_name = name
                break

    if not profile:
        avail = ", ".join(workspaces.keys()) if workspaces else "none"
        return f"Workspace profile '{profile_name}' not found. Available profiles: {avail}."

    app_aliases = config.get("app_aliases", {})
    url_aliases = config.get("url_aliases", {})

    launched_items = []

    # Launch Apps
    for app_name in profile.get("apps", []):
        try:
            apps.open_app(app_name, app_aliases)
            launched_items.append(app_name)
        except Exception as e:
            logger.warning("Failed launching workspace app %s: %s", app_name, e)

    # Launch URLs
    for url_target in profile.get("urls", []):
        try:
            urls.open_url(url_target, url_aliases)
            launched_items.append(url_target)
        except Exception as e:
            logger.warning("Failed opening workspace URL %s: %s", url_target, e)

    # Launch Playlist if specified
    if profile.get("playlist"):
        playlist_dir = config.get("local_playlist_dir", r"C:\Users\Abinesh\Music\My_playlist")
        try:
            media.play_local_playlist(playlist_dir, shuffle=True)
            launched_items.append("playlist")
        except Exception as e:
            logger.warning("Failed starting workspace playlist: %s", e)

    custom_msg = profile.get("message")
    if custom_msg:
        return custom_msg

    items_str = ", ".join(launched_items) if launched_items else "required tools"
    return f"{profile_name.capitalize()} workspace activated. Launched {items_str}."


def start_focus_session(duration_minutes: int, config: dict[str, Any], label: str = "Focus session") -> str:
    """
    Start a focused Pomodoro or deep-work session:
    - Sets a timer for the given duration.
    - Optionally adjusts volume or lowers distractions.
    """
    if duration_minutes <= 0:
        duration_minutes = 25

    duration_seconds = duration_minutes * 60
    timer_res = timer.create_timer(duration_seconds, label)

    # Adjust volume down slightly to prevent sudden loud notification sounds
    try:
        system.set_volume_percent(30)
    except Exception:
        pass

    return f"Focus mode initiated for {duration_minutes} minutes. Distractions minimized and {timer_res.lower()} Stay sharp!"


def list_workspaces(config: dict[str, Any]) -> str:
    """Return a speech-friendly list of configured workspaces."""
    workspaces = config.get("workspaces", {})
    if not workspaces:
        return "No workspace profiles configured yet."
    names = ", ".join(workspaces.keys())
    return f"Configured workspaces: {names}."
