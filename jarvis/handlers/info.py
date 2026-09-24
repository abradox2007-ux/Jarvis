"""ac/handlers/info.py — Time, date, and weather queries."""

from __future__ import annotations

import time

import re
import requests


def tell_time() -> str:
    return f"The time is {time.strftime('%I:%M %p')}."


def tell_date() -> str:
    return f"Today is {time.strftime('%A, %B %d, %Y')}."


def tell_weather(city: str, country: str) -> str:
    """Fetch current weather from wttr.in (no API key needed)."""
    try:
        url = f"https://wttr.in/{city},{country}?format=3"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        weather_text = resp.text.strip()
        # wttr.in format: "City: ⛅  +28°C"
        # Make it speech-friendly
        clean = weather_text.replace("°C", " degrees Celsius").replace("°F", " degrees Fahrenheit").replace("°", " degrees ")
        clean = clean.replace("+", "")
        clean = re.sub(r"[^\x00-\x7F]+", " ", clean)
        clean = " ".join(clean.split())
        return f"The weather in {city}: {clean}."
    except Exception as exc:
        return f"Couldn't fetch weather right now. {exc}"


def generate_startup_briefing(config: dict) -> str:
    """Generate a crisp, in-character Iron Man style J.A.R.V.I.S. startup briefing."""
    import datetime

    title = config.get("user_title", "Sir")
    now = datetime.datetime.now()
    hour = now.hour

    if 5 <= hour < 12:
        salutation = "Good morning"
    elif 12 <= hour < 17:
        salutation = "Good afternoon"
    elif 17 <= hour < 22:
        salutation = "Good evening"
    else:
        salutation = "Online and at your service"

    details = []

    # 1. Battery status if available
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery:
            plugged = "plugged in" if battery.power_plugged else "on battery power"
            details.append(f"Power levels are at {battery.percent}% ({plugged})")
    except Exception:
        pass

    # 2. Check pending diary / tasks
    try:
        from jarvis.handlers.diary import DIARY_PATH
        if DIARY_PATH.exists():
            content = DIARY_PATH.read_text(encoding="utf-8", errors="ignore").strip()
            today_str = now.strftime("%Y-%m-%d")
            if today_str in content:
                details.append("You have active notes recorded in your diary for today")
    except Exception:
        pass

    detail_str = f" {'. '.join(details)}. " if details else " "
    return f"{salutation}, {title}. All core systems are operational.{detail_str}How may I assist you?"
