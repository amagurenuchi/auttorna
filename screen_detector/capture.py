from __future__ import annotations

import ctypes
import ctypes.wintypes
from dataclasses import dataclass
import time
from threading import Lock
from typing import Iterator, Protocol
from multiprocessing import shared_memory
import struct

import numpy as np


@dataclass(frozen=True)
class CaptureTarget:
    left: int
    top: int
    width: int
    height: int
    name: str


@dataclass(frozen=True)
class CaptureFrame:
    frame: np.ndarray
    captured_at_ns: int
    target: CaptureTarget


class Capture(Protocol):
    def read(self) -> CaptureFrame: ...
    def close(self) -> None: ...


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
    def __init__(self, source: str = "monitor", monitor: int = 1, window_title: str = "", backend: str = "pillow", roi: tuple[int, int, int, int] | None = None) -> None:
        self.source, self.monitor, self.window_title, self.backend, self.roi = source, monitor, window_title, backend, roi
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

    def read(self) -> CaptureFrame:
        t = self.target()
        if self.backend == "pillow":
            from PIL import ImageGrab
            image = np.asarray(ImageGrab.grab(bbox=(t.left, t.top, t.left + t.width, t.top + t.height), include_layered_windows=True))
            frame = image[:, :, :3].copy()
        else:
            if self._sct is None:
                import mss; self._sct = mss.mss()
            image = np.asarray(self._sct.grab({"left": t.left, "top": t.top, "width": t.width, "height": t.height}))
            frame = image[:, :, :3][:, :, ::-1].copy()
        captured_at_ns = time.perf_counter_ns()
        if self.roi is not None:
            x, y, width, height = self.roi
            x2, y2 = min(frame.shape[1], x + width), min(frame.shape[0], y + height)
            if x < 0 or y < 0 or x >= x2 or y >= y2:
                raise RuntimeError("ROI does not intersect the captured target")
            frame = frame[y:y2, x:x2]
        return CaptureFrame(frame, captured_at_ns, t)

    def close(self) -> None:
        if self._sct is not None: self._sct.close()


class DxCamCapture(ScreenCapture):
    """DXCam latest-frame capture for Windows Desktop Duplication.

    DXCam is optional so the existing Pillow/mss path remains usable while the
    capture backend is being validated on a particular display setup.
    """

    def __init__(self, source: str = "monitor", monitor: int = 1, window_title: str = "", roi: tuple[int, int, int, int] | None = None, target_fps: int = 60) -> None:
        super().__init__(source, monitor, window_title, "dxcam", roi)
        if source != "monitor":
            raise RuntimeError("DXCam backend currently supports monitor capture; use wgc or mss for window capture")
        try:
            import dxcam
        except ImportError as exc:
            raise RuntimeError("Install the optional DXCam backend with: python -m pip install dxcam") from exc
        target = self.target()
        self._camera = dxcam.create(output_idx=max(0, monitor - 1), output_color="RGB")
        region = (target.left, target.top, target.left + target.width, target.top + target.height)
        self._camera.start(region=region, target_fps=target_fps, video_mode=True)

    def read(self) -> CaptureFrame:
        frame = self._camera.get_latest_frame()
        if frame is None:
            raise RuntimeError("DXCam has not produced a frame yet")
        captured_at_ns = time.perf_counter_ns()
        target = self.target()
        frame = np.asarray(frame, dtype=np.uint8)
        if self.roi is not None:
            x, y, width, height = self.roi
            frame = frame[y:y + height, x:x + width]
        return CaptureFrame(frame, captured_at_ns, target)

    def close(self) -> None:
        if getattr(self, "_camera", None) is not None:
            self._camera.stop()
            self._camera = None


class WindowsGraphicsCapture(ScreenCapture):
    """Explicit placeholder for the optional per-window WGC implementation.

    WGC requires a native WinRT capture loop and is kept separate from the
    tested Pillow/mss compatibility path until that dependency is selected.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("Windows Graphics Capture backend is not installed; use dxcam, pillow, or mss")


def create_capture(settings: object) -> Capture:
    backend = getattr(settings, "capture_backend", "pillow")
    kwargs = {
        "source": getattr(settings, "capture_source", "monitor"),
        "monitor": getattr(settings, "monitor", 1),
        "window_title": getattr(settings, "window_title", ""),
        "roi": getattr(settings, "roi", None),
    }
    if backend == "dxcam":
        return DxCamCapture(**kwargs, target_fps=getattr(settings, "max_fps", 30))
    if backend == "wgc":
        return WindowsGraphicsCapture(**kwargs)
    return ScreenCapture(**kwargs, backend=backend)


class LatestFrameSlot:
    """One-item overwrite buffer; stale frames are intentionally discarded."""

    def __init__(self) -> None:
        self._value: CaptureFrame | None = None
        self._lock = Lock()

    def publish(self, value: CaptureFrame) -> None:
        with self._lock:
            self._value = value

    def get_latest(self) -> CaptureFrame | None:
        with self._lock:
            value = self._value
            self._value = None
            return value


class SharedMemoryFrameSlot:
    """Fixed-shape shared-memory frame slot for the later process pipeline.

    The slot uses a small sequence header. Writers publish an odd sequence while
    writing and an even sequence when complete; readers retry if an overwrite is
    observed. The returned array is a view into shared memory and must be copied
    by a consumer that needs to retain it across the next publish.
    """

    _HEADER = struct.Struct("QQ")  # sequence, capture timestamp

    def __init__(self, shape: tuple[int, int, int], name: str | None = None, create: bool = True) -> None:
        if len(shape) != 3 or shape[2] != 3 or any(int(value) <= 0 for value in shape):
            raise ValueError("shape must be a positive HxWx3 frame shape")
        self.shape = tuple(int(value) for value in shape)
        size = self._HEADER.size + int(np.prod(self.shape, dtype=np.int64))
        self._owner = create
        self._shm = shared_memory.SharedMemory(name=name, create=create, size=size if create else 0)
        self._buffer = np.ndarray(self.shape, dtype=np.uint8, buffer=self._shm.buf, offset=self._HEADER.size)
        self._lock = Lock()

    @property
    def name(self) -> str:
        return self._shm.name

    def publish(self, frame: CaptureFrame) -> None:
        if frame.frame.shape != self.shape or frame.frame.dtype != np.uint8:
            raise ValueError(f"expected uint8 frame with shape {self.shape}, got {frame.frame.dtype} {frame.frame.shape}")
        with self._lock:
            sequence, _ = self._HEADER.unpack_from(self._shm.buf, 0)
            self._HEADER.pack_into(self._shm.buf, 0, sequence + 1 if sequence % 2 == 0 else sequence + 2, frame.captured_at_ns)
            np.copyto(self._buffer, frame.frame, casting="no")
            sequence = sequence + 2 if sequence % 2 == 0 else sequence + 3
            self._HEADER.pack_into(self._shm.buf, 0, sequence, frame.captured_at_ns)

    def read_latest(self) -> tuple[np.ndarray, int] | None:
        for _ in range(3):
            sequence_before, timestamp = self._HEADER.unpack_from(self._shm.buf, 0)
            if sequence_before == 0 or sequence_before % 2:
                return None
            view = self._buffer
            sequence_after, timestamp_after = self._HEADER.unpack_from(self._shm.buf, 0)
            if sequence_before == sequence_after and timestamp == timestamp_after:
                return view, timestamp
        return None

    def close(self) -> None:
        self._shm.close()

    def unlink(self) -> None:
        if self._owner:
            self._shm.unlink()
