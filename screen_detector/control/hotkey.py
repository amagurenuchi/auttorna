from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import threading
from typing import Callable


class GlobalKillSwitch:
    """Dedicated RegisterHotKey message loop for immediate disarm."""

    def __init__(self, callback: Callable[[], None], virtual_key: int = 0x7B, hotkey_id: int = 0xA771) -> None:
        self.callback = callback
        self.virtual_key = virtual_key
        self.hotkey_id = hotkey_id
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if os.name != "nt":
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="auttorna-kill-switch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, self.hotkey_id, 0, self.virtual_key):
            return
        try:
            message = ctypes.wintypes.MSG()
            while not self._stop.is_set():
                if user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    if message.message == 0x0312 and message.wParam == self.hotkey_id:
                        self.callback()
                    user32.TranslateMessage(ctypes.byref(message))
                    user32.DispatchMessageW(ctypes.byref(message))
                if self._stop.wait(0.01):
                    break
        finally:
            user32.UnregisterHotKey(None, self.hotkey_id)
