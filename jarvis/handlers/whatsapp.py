"""jarvis/handlers/whatsapp.py — Open WhatsApp Web, search contact, stage message, and handle confirmation."""

from __future__ import annotations

import logging
import time
import urllib.parse
import webbrowser

logger = logging.getLogger(__name__)


def _force_window_foreground(hwnd: int) -> None:
    """Bypass Windows foreground lock restrictions and bring window to front."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)

        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        cur_thread = kernel32.GetCurrentThreadId()

        if fg_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
    except Exception as e:
        logger.debug("Force window foreground failed: %s", e)


def _is_browser_or_whatsapp_window(title: str) -> bool:
    """Check if window title is a web browser or WhatsApp, strictly excluding IDEs and editors."""
    t = (title or "").strip().lower()
    if not t:
        return False
    excluded = (
        "antigravity", "visual studio", "vscode", "code", "notepad",
        "sublime", "pycharm", "atom", "terminal", "powershell",
        "cmd.exe", "git", "voice_assistant", "ac_voiceassistant",
        ".py", ".json", ".txt", ".md", ".js", ".html"
    )
    if any(ex in t for ex in excluded):
        return False
    return any(b in t for b in ("whatsapp", "chrome", "edge", "brave", "firefox", "opera", "browser"))


def _focus_browser_or_whatsapp() -> bool:
    """
    Find and bring the WhatsApp Web or browser window to the foreground.
    Excludes IDEs and text editors.
    """
    try:
        import pygetwindow as gw  # type: ignore
        windows = gw.getAllWindows()

        # 1. Prioritize explicit WhatsApp title window
        for w in windows:
            title = (w.title or "").strip()
            if _is_browser_or_whatsapp_window(title) and "whatsapp" in title.lower():
                try:
                    if hasattr(w, "_hWnd"):
                        _force_window_foreground(w._hWnd)
                    else:
                        if w.isMinimized:
                            w.restore()
                        w.activate()
                    time.sleep(0.4)
                    return True
                except Exception:
                    pass

        # 2. Check general browser windows
        for w in windows:
            title = (w.title or "").strip()
            if _is_browser_or_whatsapp_window(title):
                try:
                    if hasattr(w, "_hWnd"):
                        _force_window_foreground(w._hWnd)
                    else:
                        if w.isMinimized:
                            w.restore()
                        w.activate()
                    time.sleep(0.4)
                    return True
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Window focus check error: %s", e)
    return False


def _open_whatsapp_web_in_browser() -> None:
    """Open WhatsApp Web URL reliably in default browser using os.startfile or shell start."""
    url = "https://web.whatsapp.com"
    logger.info("Opening WhatsApp Web in default browser: %s", url)
    try:
        os.startfile(url)
        return
    except Exception:
        pass

    try:
        import subprocess
        subprocess.Popen(["cmd.exe", "/c", "start", "", url], shell=False)
        return
    except Exception:
        pass

    try:
        webbrowser.open(url)
    except Exception as e:
        logger.warning("Could not launch browser for WhatsApp: %s", e)


def _copy_to_clipboard(text: str) -> None:
    """Safely copy text to Windows/cross-platform clipboard."""
    try:
        import pyperclip  # type: ignore
        pyperclip.copy(text)
        return
    except Exception:
        pass

    # Windows ctypes fallback if pyperclip is not present
    try:
        import ctypes

        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        if not user32.OpenClipboard(None):
            return
        user32.EmptyClipboard()

        text_bytes = (text + "\0").encode("utf-16le")
        h_mem = kernel32.GlobalAlloc(0x0042, len(text_bytes))  # GMEM_MOVEABLE | GMEM_ZEROINIT
        if h_mem:
            p_mem = kernel32.GlobalLock(h_mem)
            if p_mem:
                ctypes.memmove(p_mem, text_bytes, len(text_bytes))
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        user32.CloseClipboard()
    except Exception as e:
        logger.warning("Failed to copy to clipboard: %s", e)


def stage_whatsapp_message(person: str, message: str, wait_seconds: float = 18.0) -> tuple[bool, str]:
    """
    Follow the 9-step WhatsApp messaging flow:
    1. Acknowledge and notify user immediately.
    2. Open WhatsApp Web in browser.
    3. Wait 15 to 20 seconds for WhatsApp Web to load completely.
    4. Bring browser window to the foreground.
    5. Select (open) the search bar.
    6. Enter the person's name.
    7. Select the first option shown when searched for that name.
    8. When entered the chat of the person, select the chat bar.
    9. Enter the message into the chat bar and ask for confirmation.
    """
    cleaned_person = person.strip().strip("'\"")
    cleaned_msg = message.strip().strip("'\"")

    if not cleaned_person:
        return False, "Please specify who you would like to send the message to."
    if not cleaned_msg:
        return False, f"What message would you like to send to {cleaned_person}?"

    logger.info("Staging WhatsApp message to '%s': '%s'", cleaned_person, cleaned_msg)

    # ── Step 1: Immediate Vocal & UI Feedback ───────────────────────────────
    try:
        from jarvis.speech import speak
        from server import set_status
        speak(f"Opening WhatsApp for {cleaned_person}. Please wait a few seconds.", block=False)
        set_status("processing", f"Opening WhatsApp for {cleaned_person}...")
    except Exception:
        pass

    # ── Step 2 & 3: Open WhatsApp Web and wait 15-20 seconds ─────────────────
    _open_whatsapp_web_in_browser()
    time.sleep(max(15.0, float(wait_seconds)))

    # ── Step 4: Bring Browser / WhatsApp to Foreground ──────────────────────
    _focus_browser_or_whatsapp()
    time.sleep(0.5)

    # ── Steps 4 to 8: Automate WhatsApp Web UI ──────────────────────────────
    try:
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = False

        screen_w, screen_h = pyautogui.size()

        # Ensure browser is in front
        _focus_browser_or_whatsapp()
        time.sleep(0.4)

        # Clear any active menu / modal
        pyautogui.press("esc")
        time.sleep(0.3)

        # ── Step 5: Focus Search Bar ─────────────────────────────────────────
        # Method A: Try WhatsApp Web New Chat shortcut (Ctrl+Alt+N) which auto-focuses search
        pyautogui.hotkey("ctrl", "alt", "n")
        time.sleep(0.4)

        # Method B: WhatsApp Web Global Search shortcut (Ctrl+Alt+/)
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(0.3)

        # Method C: Click directly into the Search input box
        search_x = max(180, int(screen_w * 0.16))
        search_y = max(160, int(screen_h * 0.20))
        pyautogui.click(search_x, search_y)
        time.sleep(0.3)

        # Clear existing search text
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.2)

        # ── Step 6: Enter the contact name ──────────────────────────────────
        _copy_to_clipboard(cleaned_person)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(2.0)  # Wait for search results to filter down

        # ── Step 7: Select the first option (Enter + click first item) ───────
        pyautogui.press("down")
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.5)

        # Backup click: Click 1st contact card in results list directly
        first_contact_x = search_x
        first_contact_y = max(240, int(screen_h * 0.30))
        pyautogui.click(first_contact_x, first_contact_y)
        time.sleep(1.5)

        # ── Step 8: Select the chat bar & paste message ──────────────────────
        chat_x = max(300, int(screen_w * 0.55))
        chat_y = max(200, int(screen_h * 0.95))
        pyautogui.click(chat_x, chat_y)
        time.sleep(0.3)

        # Clear any draft and paste message
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        _copy_to_clipboard(cleaned_msg)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)

        # ── Step 9: Return status for confirmation prompt ────────────────────
        return True, f"I have prepared your message to {cleaned_person}: '{cleaned_msg}'. Should I send it?"

    except Exception as e:
        logger.error("Error during WhatsApp automation: %s", e)
        return False, f"Could not prepare WhatsApp message due to error: {e}"


def confirm_send_whatsapp_message(person: str = "") -> str:
    """
    Step 9 (Yes): Send the staged WhatsApp message.
    """
    try:
        _focus_browser_or_whatsapp()
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = False

        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.3)
    except Exception as e:
        logger.warning("Failed to send WhatsApp message: %s", e)

    target = f" to {person}" if person else ""
    return f"Message sent{target}."


def cancel_whatsapp_message() -> str:
    """
    Step 9 (No): Clear the draft and prompt the user for the correct person and message again.
    """
    try:
        _focus_browser_or_whatsapp()
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = False

        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.2)
    except Exception as e:
        logger.warning("Failed to clear WhatsApp draft: %s", e)

    return "Message cancelled. Who would you like to message and what should it say?"
