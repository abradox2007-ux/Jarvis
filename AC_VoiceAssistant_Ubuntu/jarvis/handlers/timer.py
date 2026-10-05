"""jarvis/handlers/timer.py — Non-blocking timer, countdown, and voice reminder engine."""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Active timers store: {id: {"id": str, "label": str, "duration": int, "start_time": float, "thread": Timer}}
_active_timers: dict[str, dict] = {}
_timer_lock = threading.Lock()


def parse_time_duration(text: str) -> Optional[tuple[int, str]]:
    """
    Parse a natural language text for timer duration and optional label.
    Examples:
      - "set a timer for 5 minutes" -> (300, "Timer for 5 minutes")
      - "timer 30 seconds" -> (30, "Timer for 30 seconds")
      - "remind me to call John in 1 hour and 30 minutes" -> (5400, "call John")
      - "set a 10 second timer" -> (10, "Timer for 10 seconds")
    """
    # Extract reminder label if present (e.g. "remind me to <label> in <time>")
    remind_match = re.search(r"remind\s+(?:me\s+)?(?:to\s+)?(.+?)\s+(?:in|after)\s+(.+)", text, re.IGNORECASE)
    if remind_match:
        label = remind_match.group(1).strip()
        time_part = remind_match.group(2).strip().lower()
    else:
        label = "Timer"
        time_part = text.strip().lower()

    total_seconds = 0
    found_any = False

    # Hours
    hr_match = re.search(r"(\d+)\s*(?:hours?|hrs?|hr)", time_part)
    if hr_match:
        total_seconds += int(hr_match.group(1)) * 3600
        found_any = True

    # Minutes
    min_match = re.search(r"(\d+)\s*(?:minutes?|mins?|min)", time_part)
    if min_match:
        total_seconds += int(min_match.group(1)) * 60
        found_any = True

    # Seconds
    sec_match = re.search(r"(\d+)\s*(?:seconds?|secs?|sec)", time_part)
    if sec_match:
        total_seconds += int(sec_match.group(1))
        found_any = True

    # Standalone number assuming minutes if no units found but "timer for 5"
    if not found_any:
        simple_match = re.search(r"(?:timer|remind me).*?\s+(\d+)\s*$", text.strip().lower())
        if simple_match:
            total_seconds = int(simple_match.group(1)) * 60
            found_any = True

    if found_any and total_seconds > 0:
        if label == "Timer":
            dur_str = f"{total_seconds} seconds" if total_seconds < 60 else f"{total_seconds // 60} minutes"
            label = f"Timer for {dur_str}"
        return total_seconds, label

    return None


def create_timer(seconds: int, label: str, on_complete: Optional[Callable[[str], None]] = None) -> str:
    """Create and start a background countdown timer."""
    timer_id = str(uuid.uuid4())[:8]

    def _timer_finished():
        with _timer_lock:
            _active_timers.pop(timer_id, None)
        logger.info("Timer expired: %s (%s)", label, timer_id)
        
        # Trigger speech and notification
        try:
            from jarvis.speech import speak
            msg = f"Alert: Your {label} is done!"
            speak(msg)
        except Exception as e:
            logger.warning("Could not speak timer completion: %s", e)

        if on_complete:
            try:
                on_complete(label)
            except Exception as e:
                logger.warning("Timer on_complete callback failed: %s", e)

    t = threading.Timer(float(seconds), _timer_finished)
    t.daemon = True

    with _timer_lock:
        _active_timers[timer_id] = {
            "id": timer_id,
            "label": label,
            "duration": seconds,
            "start_time": time.time(),
            "remaining": seconds,
            "thread": t
        }

    t.start()
    
    # Format readable duration
    if seconds >= 3600:
        dur_desc = f"{seconds // 3600} hours and {(seconds % 3600) // 60} minutes"
    elif seconds >= 60:
        dur_desc = f"{seconds // 60} minutes and {seconds % 60} seconds" if seconds % 60 else f"{seconds // 60} minutes"
    else:
        dur_desc = f"{seconds} seconds"

    return f"Timer set for {dur_desc}."


def get_active_timers() -> list[dict]:
    """Return a list of currently active timers with remaining seconds."""
    with _timer_lock:
        now = time.time()
        result = []
        for tid, data in _active_timers.items():
            elapsed = now - data["start_time"]
            remaining = max(0, int(data["duration"] - elapsed))
            result.append({
                "id": tid,
                "label": data["label"],
                "duration": data["duration"],
                "remaining": remaining
            })
        return sorted(result, key=lambda x: x["remaining"])


def list_timers() -> str:
    """Return a speech-friendly summary of all running timers."""
    timers = get_active_timers()
    if not timers:
        return "You have no active timers."
    if len(timers) == 1:
        t = timers[0]
        rem = t["remaining"]
        rem_str = f"{rem // 60} minutes and {rem % 60} seconds" if rem >= 60 else f"{rem} seconds"
        return f"You have 1 active timer for {t['label']} with {rem_str} remaining."
    summary = [f"{t['label']} with {t['remaining']}s left" for t in timers]
    return f"You have {len(timers)} active timers: " + ", ".join(summary)


def cancel_all_timers() -> str:
    """Cancel all running timers."""
    with _timer_lock:
        count = len(_active_timers)
        for data in list(_active_timers.values()):
            try:
                data["thread"].cancel()
            except Exception:
                pass
        _active_timers.clear()
        return f"Cancelled {count} active timer(s)." if count > 0 else "No active timers to cancel."
