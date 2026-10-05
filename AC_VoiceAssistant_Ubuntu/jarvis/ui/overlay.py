"""jarvis/ui/overlay.py — Transparent visual overlay displaying numbered badges over UI elements."""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time

logger = logging.getLogger(__name__)

_overlay_instance: BadgeOverlay | None = None
_instance_lock = threading.Lock()


class BadgeOverlay:
    """
    Transparent, topmost overlay window that draws high-contrast numbered badges
    over detected input fields on screen.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._root = None
        self._canvas = None
        self._running = False
        self._is_visible = False
        self._auto_hide_timer = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_tk_loop, daemon=True, name="BadgeOverlayThread")
        self._thread.start()

    def _run_tk_loop(self) -> None:
        try:
            import tkinter as tk
            self._root = tk.Tk()
            self._root.title("Jarvis UI Overlay")
            self._root.attributes("-topmost", True)
            self._root.overrideredirect(True)

            # Get screen dimensions
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
            self._root.geometry(f"{screen_w}x{screen_h}+0+0")

            # Make background transparent on Windows
            trans_color = "#000001"
            if sys.platform == "win32":
                try:
                    self._root.wm_attributes("-transparentcolor", trans_color)
                except Exception:
                    pass

            self._root.config(bg=trans_color)
            self._canvas = tk.Canvas(
                self._root,
                width=screen_w,
                height=screen_h,
                bg=trans_color,
                highlightthickness=0
            )
            self._canvas.pack(fill="both", expand=True)

            # Start queue processor
            self._root.after(50, self._process_queue)
            self._root.withdraw()
            self._root.mainloop()
        except Exception as e:
            logger.debug("Overlay Tkinter loop ended: %s", e)
        finally:
            self._running = False

    def _process_queue(self) -> None:
        try:
            while not self._queue.empty():
                action, data = self._queue.get_nowait()
                if action == "show":
                    self._render_badges(data)
                elif action == "hide":
                    self._clear_badges()
                elif action == "quit":
                    if self._root:
                        self._root.quit()
                    return
        except Exception as e:
            logger.debug("Overlay queue error: %s", e)

        if self._root and self._running:
            self._root.after(50, self._process_queue)

    def _render_badges(self, fields: list[dict]) -> None:
        if not self._root or not self._canvas:
            return

        self._canvas.delete("all")
        self._root.deiconify()
        self._root.lift()
        self._root.attributes("-topmost", True)
        self._is_visible = True

        for item in fields:
            idx = item.get("index", 1)
            rect = item.get("rect")
            if not rect:
                continue
            left, top, right, bottom = rect

            # Position badge pill slightly above or at top-left of the bounding box
            badge_x = max(10, left + 4)
            badge_y = max(10, top - 24 if top >= 28 else top + 4)
            badge_w = 34
            badge_h = 24
            r = 6  # rounded corner radius

            # Draw outer glow / border rectangle
            self._canvas.create_rectangle(
                badge_x - 1, badge_y - 1,
                badge_x + badge_w + 1, badge_y + badge_h + 1,
                fill="#38BDF8", outline="#0284C7", width=2
            )

            # Draw dark inner pill
            self._canvas.create_rectangle(
                badge_x + 1, badge_y + 1,
                badge_x + badge_w - 1, badge_y + badge_h - 1,
                fill="#0F172A", outline="#1E293B", width=1
            )

            # Draw prominent number text
            self._canvas.create_text(
                badge_x + badge_w // 2,
                badge_y + badge_h // 2,
                text=str(idx),
                fill="#FFFFFF",
                font=("Segoe UI", 11, "bold")
            )

            # Optional subtle bounding highlight around the input field itself
            self._canvas.create_rectangle(
                left, top, right, bottom,
                outline="#38BDF8",
                width=2,
                dash=(4, 4)
            )

    def _clear_badges(self) -> None:
        if not self._root or not self._canvas:
            return
        self._canvas.delete("all")
        self._root.withdraw()
        self._is_visible = False

    def show_badges(self, fields: list[dict], auto_hide_sec: float = 15.0) -> None:
        """Render badge numbers above target field bounding boxes."""
        self.start()
        self._queue.put(("show", fields))

    def hide_badges(self) -> None:
        """Dismiss and hide the overlay window."""
        self._queue.put(("hide", None))

    def is_visible(self) -> bool:
        return self._is_visible

    def close(self) -> None:
        self._queue.put(("quit", None))


def get_badge_overlay() -> BadgeOverlay:
    """Return singleton BadgeOverlay instance."""
    global _overlay_instance
    with _instance_lock:
        if _overlay_instance is None:
            _overlay_instance = BadgeOverlay()
        return _overlay_instance
