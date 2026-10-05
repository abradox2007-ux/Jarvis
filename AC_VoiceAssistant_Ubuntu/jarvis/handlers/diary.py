"""ac/handlers/diary.py — Append diary entries to data/Diary.txt."""

from __future__ import annotations

import time
from pathlib import Path

DIARY_PATH = Path(__file__).parent.parent.parent / "data" / "Diary.txt"


def append_diary_entry(text: str) -> str:
    """Append *text* with a timestamp to the diary file. Returns spoken response."""
    if not text.strip():
        return "What would you like to add to your diary?"

    DIARY_PATH.parent.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n[{timestamp}]\n{text.strip()}\n"

    with open(DIARY_PATH, "a", encoding="utf-8") as f:
        f.write(entry)

    return "Added to your diary."


append_diary = append_diary_entry


def open_diary() -> str:
    """Open the diary file in the default text viewer. Returns spoken response."""
    import os
    if not DIARY_PATH.exists():
        DIARY_PATH.parent.mkdir(exist_ok=True)
        with open(DIARY_PATH, "w", encoding="utf-8") as f:
            f.write("=== My Voice Assistant Diary ===\n")
    from jarvis.utils import open_file_crossplatform
    if open_file_crossplatform(DIARY_PATH):
        return "Opening your diary."
    return "Couldn't open the diary file."


def get_diary_entries() -> list[dict[str, str | int]]:
    """Parse Diary.txt and return a list of entries with index, timestamp, and text."""
    if not DIARY_PATH.exists():
        return []
    
    with open(DIARY_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    import re
    # Entries start with [YYYY-MM-DD HH:MM:SS]
    pattern = r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\n(.*?)(?=\n\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]|\Z)"
    matches = re.finditer(pattern, content, re.DOTALL)
    
    entries = []
    for idx, match in enumerate(matches):
        timestamp = match.group(1)
        text = match.group(2).strip()
        entries.append({
            "index": idx,
            "timestamp": timestamp,
            "text": text
        })
    return entries


def save_diary_entries(entries: list[dict]) -> None:
    """Save the list of entries back to Diary.txt."""
    DIARY_PATH.parent.mkdir(exist_ok=True)
    with open(DIARY_PATH, "w", encoding="utf-8") as f:
        f.write("=== My Voice Assistant Diary ===\n")
        for entry in entries:
            timestamp = entry["timestamp"]
            text = entry["text"].strip()
            f.write(f"\n[{timestamp}]\n{text}\n")


def update_entry(index: int, text: str) -> bool:
    """Update entry at index with new text."""
    entries = get_diary_entries()
    if 0 <= index < len(entries):
        entries[index]["text"] = text.strip()
        save_diary_entries(entries)
        return True
    return False


def delete_entry(index: int) -> bool:
    """Delete entry at index."""
    entries = get_diary_entries()
    if 0 <= index < len(entries):
        entries.pop(index)
        save_diary_entries(entries)
        return True
    return False
