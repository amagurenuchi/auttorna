from __future__ import annotations

import ctypes
import ctypes.wintypes
from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass(frozen=True)
class CaptureTarget:
    left: int
    top: int
    width: int
    height: int
    name: str


def windows() -> list[str]:
    if not hasattr(ctypes, "windll"): return []
    user32 = ctypes.windll.user32
    result: list[str] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd: int, _: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1); user32.GetWindowTextW(hwnd, buf, n + 1)
                result.append(buf.value)
        return True
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return result


class ScreenCapture:
    def __init__(self, source: str = "monitor", monitor: int = 1, window_title: str = "", backend: str = "pillow") -> None:
        self.source, self.monitor, self.window_title, self.backend = source, monitor, window_title, backend
        self._sct = None

    def target(self) -> CaptureTarget:
        import mss
        if self._sct is None: self._sct = mss.mss()
        if self.source == "monitor":
            monitors = self._sct.monitors
            if self.monitor < 1 or self.monitor >= len(monitors): raise RuntimeError(f"Monitor {self.monitor} is unavailable")
            m = monitors[self.monitor]
            return CaptureTarget(m["left"], m["top"], m["width"], m["height"], f"Monitor {self.monitor}")
        if not hasattr(ctypes, "windll"): raise RuntimeError("Window capture requires Windows")
        user32 = ctypes.windll.user32; found = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def callback(hwnd: int, _: int) -> bool:
            n = user32.GetWindowTextLengthW(hwnd); buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if user32.IsWindowVisible(hwnd) and self.window_title.lower() in buf.value.lower(): found.append((hwnd, buf.value))
            return True
        user32.EnumWindows(WNDENUMPROC(callback), 0)
        if not found: raise RuntimeError(f"Window not found: {self.window_title}")
        rect = ctypes.wintypes.RECT(); user32.GetWindowRect(found[0][0], ctypes.byref(rect))
        return CaptureTarget(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top, found[0][1])

    def read(self) -> tuple[np.ndarray, CaptureTarget]:
        t = self.target()
        if self.backend == "pillow":
            from PIL import ImageGrab
            image = np.asarray(ImageGrab.grab(bbox=(t.left, t.top, t.left + t.width, t.top + t.height), include_layered_windows=True))
            return image[:, :, :3].copy(), t
        if self._sct is None:
            import mss; self._sct = mss.mss()
        image = np.asarray(self._sct.grab({"left": t.left, "top": t.top, "width": t.width, "height": t.height}))
        return image[:, :, :3][:, :, ::-1].copy(), t

    def close(self) -> None:
        if self._sct is not None: self._sct.close()
