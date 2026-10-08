"""jarvis/handlers/gui.py — GUI and desktop automation tools (hotkeys, copy, paste, typing)."""

from __future__ import annotations

import logging
import re
import time

try:
    import pyautogui
    pyautogui.FAILSAFE = False
except Exception:
    pyautogui = None

try:
    import pyperclip
except Exception:
    pyperclip = None

logger = logging.getLogger(__name__)


def press_hotkey(keys: str) -> str:
    """Simulate a keyboard shortcut or key combination (e.g. 'ctrl+c', 'alt+tab', 'enter')."""
    if not keys or not str(keys).strip():
        return "No key combination specified."

    clean = str(keys).strip().lower()
    # Normalize aliases
    clean = clean.replace("control", "ctrl").replace("command", "ctrl")
    parts = [k.strip() for k in re.split(r"[+,\s]+", clean) if k.strip()]

    if not parts:
        return "Invalid key combination."

    if not pyautogui:
        return "Desktop automation is not available."

    try:
        if len(parts) == 1:
            pyautogui.press(parts[0])
            return f"Pressed '{parts[0]}'."
        else:
            pyautogui.hotkey(*parts)
            return f"Executed shortcut '{'+'.join(parts)}'."
    except Exception as exc:
        logger.warning("Failed executing hotkey '%s': %s", keys, exc)
        return f"Could not execute hotkey '{keys}': {exc}"


def clipboard_action(command: str) -> str:
    """Execute standard OS clipboard operations (copy, paste, cut, select all)."""
    cmd = command.strip().lower()

    if not pyautogui:
        return "Desktop automation is not available."

    try:
        if cmd in ("copy", "copy_text", "copy_selection"):
            pyautogui.hotkey("ctrl", "c")
            return "Copied to clipboard."
        elif cmd in ("paste", "paste_text"):
            pyautogui.hotkey("ctrl", "v")
            return "Pasted from clipboard."
        elif cmd in ("cut", "cut_text"):
            pyautogui.hotkey("ctrl", "x")
            return "Cut to clipboard."
        elif cmd in ("select_all", "select all"):
            pyautogui.hotkey("ctrl", "a")
            return "Selected all."
        elif cmd in ("undo", "revert"):
            pyautogui.hotkey("ctrl", "z")
            return "Undone last action."
        elif cmd in ("save", "save_file"):
            pyautogui.hotkey("ctrl", "s")
            return "Saved document."
        else:
            return f"Unknown clipboard action '{command}'."
    except Exception as exc:
        logger.warning("Failed clipboard action '%s': %s", command, exc)
        return f"Could not execute {command}: {exc}"


def type_text(text: str, press_enter: bool = False) -> str:
    """Simulate typing text into the active focused window."""
    if not text:
        return "No text provided to type."

    if not pyautogui:
        return "Desktop automation is not available."

    try:
        if pyperclip:
            # Use clipboard paste for fast, lossless Unicode typing
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.typewrite(text, interval=0.01)

        if press_enter:
            time.sleep(0.1)
            pyautogui.press("enter")

        return f"Typed '{text[:30]}'."
    except Exception as exc:
        logger.warning("Failed typing text: %s", exc)
        return f"Failed to type text: {exc}"


def switch_window() -> str:
    """Simulate Alt+Tab to switch to the most recent window."""
    if not pyautogui:
        return "Desktop automation is not available."

    try:
        pyautogui.hotkey("alt", "tab")
        return "Switched window."
    except Exception as exc:
        return f"Failed to switch window: {exc}"
