"""ROI capture with DXCam first and MSS fallback."""

from dataclasses import dataclass
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Frame:
    captured_at: float
    pixels: object


class Capture(Protocol):
    def read(self) -> Frame | None: ...


class RoiCapture:
    def __init__(self, roi: tuple[int, int, int, int], target_hz: int = 20, backend: str = "dxcam") -> None:
        self.roi = roi
        self.period = 1.0 / target_hz
        self._last = 0.0
        self._camera = None
        self._mss = None
        self._use_dxcam = backend == "dxcam"

    def start(self) -> None:
        if self.roi[2] <= self.roi[0] or self.roi[3] <= self.roi[1]:
            raise ValueError(f"invalid ROI: {self.roi}")
        try:
            import mss
            with mss.mss() as screen:
                monitor = screen.monitors[1]
            if not (monitor["left"] <= self.roi[0] < self.roi[2] <= monitor["left"] + monitor["width"] and monitor["top"] <= self.roi[1] < self.roi[3] <= monitor["top"] + monitor["height"]):
                raise ValueError(f"ROI {self.roi} is outside the primary monitor {monitor}")
        except ImportError:
            pass
        if self._use_dxcam:
            try:
                import dxcam
                self._camera = dxcam.create(output_idx=0, region=self.roi, output_color="RGB", processor_backend="numpy")
                self._camera.start(target_fps=round(1 / self.period), video_mode=True)
                return
            except Exception as error:
                logger.warning("DXCam unavailable; falling back to MSS: %s", error)
                self._camera = None
        import mss
        self._mss = mss.mss()

    def read(self) -> Frame | None:
        import time
        now = time.perf_counter()
        if now - self._last < self.period:
            return None
        self._last = now
        left, top, right, bottom = self.roi
        if self._camera is not None:
            pixels = self._camera.get_latest_frame()
        else:
            if self._mss is None:
                self.start()
            pixels = self._mss.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
        return Frame(time.perf_counter(), pixels) if pixels is not None else None

    def close(self) -> None:
        if self._camera is not None:
            self._camera.stop()
            release = getattr(self._camera, "release", None)
            if release is not None:
                release()
            self._camera = None
        if self._mss is not None:
            self._mss.close()
