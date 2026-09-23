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


def _is_real_whatsapp_window(title: str) -> bool:
    t = (title or "").strip().lower()
    if not t:
        return False
    # Exclude code editors, IDEs, terminals, scripts, folder paths
    excluded = (
        ".py", ".json", ".txt", ".md", ".js", ".html",
        "antigravity", "visual studio", "vscode", "code", "notepad",
        "terminal", "powershell", "cmd.exe", "git",
        "voice_assistant", "ac_voiceassistant"
    )
    if any(ex in t for ex in excluded):
        return False
    return "whatsapp" in t


def _find_and_focus_whatsapp_window() -> bool:
    """
    Search if WhatsApp Web (or WhatsApp desktop app) is currently open in any window.
    Brings it to the foreground with Win32 focus lock bypass.
    Only returns True if a window explicitly has 'whatsapp' in its title and is not a code editor.
    """
    try:
        import pygetwindow as gw  # type: ignore
        windows = gw.getAllWindows()

        for w in windows:
            title = (w.title or "").strip()
            if _is_real_whatsapp_window(title):
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
    """Open WhatsApp Web URL reliably in default browser using Windows shell start."""
    url = "https://web.whatsapp.com"
    logger.info("Opening WhatsApp Web in default browser: %s", url)
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
    1. Open WhatsApp Web in browser (or switch to existing WhatsApp window).
    2. Wait 15 to 20 seconds for WhatsApp Web to load completely.
    3. Select (open) the search bar.
    4. Enter the person's name.
    5. Select the first option shown when searched for that name.
    6. When entered the chat of the person, select the chat bar.
    7. Enter the message into the chat bar.
    8. Ask whether to send or not.
    """
    cleaned_person = person.strip().strip("'\"")
    cleaned_msg = message.strip().strip("'\"")

    if not cleaned_person:
        return False, "Please specify who you would like to send the message to."
    if not cleaned_msg:
        return False, f"What message would you like to send to {cleaned_person}?"

    logger.info("Staging WhatsApp message to '%s': '%s'", cleaned_person, cleaned_msg)

    # ── Step 1 & 2: Open WhatsApp Web and wait 15-20 seconds ─────────────────
    is_already_open = _find_and_focus_whatsapp_window()
    if not is_already_open:
        logger.info("Opening WhatsApp Web in browser...")
        _open_whatsapp_web_in_browser()
        time.sleep(max(15.0, float(wait_seconds)))
        _find_and_focus_whatsapp_window()
    else:
        logger.info("WhatsApp window found. Bringing to foreground...")
        time.sleep(1.0)

    # ── Steps 3 to 7: Automate WhatsApp Web UI ──────────────────────────────
    try:
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = False

        _find_and_focus_whatsapp_window()
        screen_w, screen_h = pyautogui.size()

        # Clear any active menu / modal
        pyautogui.press("esc")
        time.sleep(0.3)

        # ── Step 3: Select (open) the search bar ─────────────────────────────
        search_x = max(150, int(screen_w * 0.18))
        search_y = max(120, int(screen_h * 0.19))
        
        # Click directly on the search bar
        pyautogui.click(search_x, search_y)
        time.sleep(0.3)

        # Send WhatsApp Web search shortcut: Ctrl+Alt+/
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(0.3)

        # ── Step 4: Enter the person's name ──────────────────────────────────
        _copy_to_clipboard(cleaned_person)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)

        # ── Step 5: Select the first option shown when searched ──────────────
        # Wait 2.0s for search results to filter down
        time.sleep(2.0)

        # Click the 1st search result item directly below search bar
        first_result_x = search_x
        first_result_y = search_y + 80
        pyautogui.click(first_result_x, first_result_y)
        time.sleep(0.4)

        # Press Enter to open the conversation
        pyautogui.press("enter")
        time.sleep(1.5)

        # ── Step 6: Select the chat bar ──────────────────────────────────────
        chat_x = max(250, int(screen_w * 0.55))
        chat_y = max(200, int(screen_h * 0.95))
        pyautogui.click(chat_x, chat_y)
        time.sleep(0.3)

        # ── Step 7: Enter the message ────────────────────────────────────────
        _copy_to_clipboard(cleaned_msg)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)

        # ── Step 8: Return status for confirmation prompt ────────────────────
        return True, f"I have prepared your message to {cleaned_person}: '{cleaned_msg}'. Should I send it?"

    except ImportError:
        logger.warning("pyautogui is not installed. Staging message via direct WhatsApp link fallback.")
        encoded_msg = urllib.parse.quote(cleaned_msg)
        webbrowser.open(f"https://web.whatsapp.com/send?text={encoded_msg}")
        return True, f"I opened WhatsApp for {cleaned_person} with your message. Should I send it?"
    except Exception as e:
        logger.error("Error during WhatsApp automation: %s", e)
        return False, f"Could not prepare WhatsApp message due to error: {e}"


def confirm_send_whatsapp_message(person: str = "") -> str:
    """
    Step 9 (Yes): Send the staged WhatsApp message.
    """
    try:
        _find_and_focus_whatsapp_window()
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = False

        screen_w, screen_h = pyautogui.size()
        time.sleep(0.3)

        # 1. Click chat bar to ensure input focus
        chat_x = max(250, int(screen_w * 0.55))
        chat_y = max(200, int(screen_h * 0.95))
        pyautogui.click(chat_x, chat_y)
        time.sleep(0.2)

        # 2. Press Enter to submit the message
        pyautogui.press("enter")
        time.sleep(0.3)

        # 3. Click the green Send button on the bottom right as guaranteed backup
        send_btn_x = max(chat_x + 50, int(screen_w * 0.97))
        send_btn_y = chat_y
        pyautogui.click(send_btn_x, send_btn_y)
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
        _find_and_focus_whatsapp_window()
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = False

        screen_w, screen_h = pyautogui.size()
        chat_x = max(250, int(screen_w * 0.55))
        chat_y = max(200, int(screen_h * 0.95))
        pyautogui.click(chat_x, chat_y)
        time.sleep(0.2)

        # Clear text in chat bar
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.2)
    except Exception as e:
        logger.warning("Failed to clear WhatsApp draft: %s", e)

    return "Message cancelled. Who would you like to message and what should it say?"
