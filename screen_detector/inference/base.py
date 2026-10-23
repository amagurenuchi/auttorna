from __future__ import annotations

from typing import Protocol

import numpy as np

from ..model import Detection


class Detector(Protocol):
    def predict(self, frame_rgb: np.ndarray) -> list[Detection]: ...

