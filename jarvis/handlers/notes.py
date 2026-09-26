"""jarvis/handlers/notes.py — Quick voice notes and thought capture handler."""

from __future__ import annotations

import datetime
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

NOTES_PATH = Path(__file__).parent.parent.parent / "data" / "quick_notes.txt"


def add_note(text: str, category: str = "General") -> str:
    """
    Append a quick note or thought with timestamp to data/quick_notes.txt.
    Returns spoken confirmation.
    """
    clean_text = text.strip()
    if not clean_text:
        return "What note would you like me to write down?"

    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d %I:%M %p")

    entry_line = f"- [{timestamp_str}] ({category}): {clean_text}\n"

    try:
        with open(NOTES_PATH, "a", encoding="utf-8") as f:
            f.write(entry_line)
        preview = clean_text if len(clean_text) <= 50 else clean_text[:47] + "..."
        return f"Noted down: {preview}"
    except Exception as e:
        logger.error("Failed writing quick note: %s", e)
        return f"Could not save note: {e}"


def read_notes(count: int = 5, today_only: bool = False) -> str:
    """
    Read the most recent quick notes or today's notes.
    """
    if not NOTES_PATH.exists():
        return "You have no notes saved yet."

    try:
        with open(NOTES_PATH, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip().startswith("- [")]

        if not lines:
            return "Your notes list is currently empty."

        now_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        if today_only:
            lines = [l for l in lines if f"[{now_date_str}" in l]
            if not lines:
                return "You haven't recorded any notes today."

        recent = lines[-count:]
        cleaned_notes = []
        for line in recent:
            # Format: - [2026-09-25 01:25 AM] (General): Note text
            m = re.match(r"^-\s*\[.*?\]\s*(?:\(.*?\):)?\s*(.*)$", line)
            if m:
                cleaned_notes.append(m.group(1).strip())
            else:
                cleaned_notes.append(line.lstrip("- "))

        notes_spoken = ". Next: ".join(cleaned_notes)
        return f"Here are your latest notes: {notes_spoken}."
    except Exception as e:
        logger.error("Failed reading notes: %s", e)
        return f"Could not read notes: {e}"


def open_notes() -> str:
    """
    Open the notes file in the default Windows text editor.
    """
    if not NOTES_PATH.exists():
        NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES_PATH, "w", encoding="utf-8") as f:
            f.write("=== Quick Notes & Thoughts ===\n")

    try:
        os.startfile(str(NOTES_PATH))
        return "Opening your quick notes."
    except Exception as e:
        logger.error("Failed to open notes file: %s", e)
        return f"Could not open notes file: {e}"
