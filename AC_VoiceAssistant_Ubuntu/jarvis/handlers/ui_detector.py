"""jarvis/handlers/ui_detector.py — Detect editable UI input fields and handle click/type automation."""

from __future__ import annotations

import ctypes
import logging
import sys
import time
import pyautogui
import pyperclip

logger = logging.getLogger(__name__)


def find_input_fields(max_fields: int = 9) -> list[dict]:
    """
    Inspect the currently active foreground window using Windows UI Automation
    and return visible, editable input bars/search boxes with screen bounding coordinates.
    """
    fields: list[dict] = []

    try:
        import uiautomation as auto
    except ImportError:
        logger.warning("uiautomation library not available.")
        return fields

    try:
        # Get active window control
        fg_ctrl = auto.GetForegroundControl()
        if not fg_ctrl:
            hwnd = ctypes.windll.user32.GetForegroundWindow() if sys.platform == "win32" else 0
            if hwnd:
                fg_ctrl = auto.ControlFromHandle(hwnd)

        if not fg_ctrl:
            logger.debug("No foreground window control identified.")
            return fields

        # Search for editable controls
        # ControlType: EditControl, ComboBoxControl, DocumentControl
        target_types = {
            auto.ControlType.EditControl,
            auto.ControlType.ComboBoxControl,
            auto.ControlType.DocumentControl,
        }

        candidates = []

        # Find all controls under the foreground window matching target types
        for ctrl, depth in auto.WalkControl(fg_ctrl, maxDepth=12):
            try:
                if ctrl.ControlType in target_types:
                    # Check if control is enabled and visible
                    if ctrl.IsEnabled and not ctrl.IsOffscreen:
                        rect = ctrl.BoundingRectangle
                        if rect:
                            w = rect.width()
                            h = rect.height()
                            # Filter out tiny invisible controls or massive entire-screen containers
                            if 20 <= w <= 1920 and 12 <= h <= 600:
                                candidates.append((ctrl, rect, w, h))
            except Exception:
                continue

        # Deduplicate overlapping or nearly identical bounding boxes
        unique_fields = []
        for ctrl, rect, w, h in candidates:
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            center_x = left + w // 2
            center_y = top + h // 2

            # Check if an existing field overlaps significantly
            is_duplicate = False
            for existing in unique_fields:
                ex_left, ex_top, ex_right, ex_bottom = existing["rect"]
                if abs(left - ex_left) < 15 and abs(top - ex_top) < 15:
                    is_duplicate = True
                    break

            if not is_duplicate:
                name = ctrl.Name.strip() if ctrl.Name else ""
                ctrl_type_name = ctrl.ControlTypeName
                unique_fields.append({
                    "name": name or f"{ctrl_type_name}",
                    "type": ctrl_type_name,
                    "rect": (left, top, right, bottom),
                    "center": (center_x, center_y),
                    "control": ctrl
                })

        # Sort top-to-bottom, left-to-right
        unique_fields.sort(key=lambda item: (item["rect"][1], item["rect"][0]))

        # Assign 1-indexed numbers and slice to max_fields
        for idx, item in enumerate(unique_fields[:max_fields], start=1):
            item["index"] = idx
            fields.append(item)

    except Exception as e:
        logger.warning("UI field detection encountered error: %s", e)

    return fields


def focus_and_click_field(field_info: dict) -> bool:
    """Focus the chosen field and click its center."""
    try:
        ctrl = field_info.get("control")
        if ctrl:
            try:
                ctrl.SetFocus()
            except Exception:
                pass

        center = field_info.get("center")
        if center:
            cx, cy = center
            pyautogui.click(cx, cy)
            return True
    except Exception as e:
        logger.warning("Failed to focus/click field: %s", e)
    return False


def type_into_field(field_info: dict, text: str, press_enter: bool = False) -> bool:
    """Focus the field, type/paste the text string, and optionally press Enter."""
    try:
        focus_and_click_field(field_info)
        time.sleep(0.08)

        # Use clipboard paste for instant typing and full Unicode / Tamil support
        pyperclip.copy(text)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.05)

        if press_enter:
            time.sleep(0.1)
            pyautogui.press('enter')

        return True
    except Exception as e:
        logger.warning("Failed to type into field: %s", e)
        # Fallback to direct pyautogui typewrite
        try:
            pyautogui.typewrite(text, interval=0.01)
            if press_enter:
                pyautogui.press('enter')
            return True
        except Exception:
            return False
