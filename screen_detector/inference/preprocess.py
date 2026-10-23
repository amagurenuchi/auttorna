from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class PreparedInput:
    tensor: np.ndarray
    source_width: int
    source_height: int


class FixedPreprocessor:
    """Reusable RGB -> NCHW float32 preprocessor with a fixed model shape."""

    def __init__(self, resolution: int, mean: tuple[float, float, float] = (0.485, 0.456, 0.406), std: tuple[float, float, float] = (0.229, 0.224, 0.225)) -> None:
        if resolution <= 0:
            raise ValueError("resolution must be positive")
        self.resolution = int(resolution)
        self.mean = np.asarray(mean, dtype=np.float32).reshape(3, 1, 1)
        self.std = np.asarray(std, dtype=np.float32).reshape(3, 1, 1)
        self._tensor = np.empty((1, 3, self.resolution, self.resolution), dtype=np.float32)

    def __call__(self, frame_rgb: np.ndarray) -> PreparedInput:
        if frame_rgb.ndim != 3 or frame_rgb.shape[2] != 3:
            raise ValueError("expected an HxWx3 RGB frame")
        height, width = frame_rgb.shape[:2]
        resized = Image.fromarray(np.ascontiguousarray(frame_rgb), mode="RGB").resize((self.resolution, self.resolution), Image.Resampling.BILINEAR)
        pixels = np.asarray(resized, dtype=np.float32) / 255.0
        chw = np.moveaxis(pixels, 2, 0)
        self._tensor[0] = (chw - self.mean) / self.std
        return PreparedInput(self._tensor, width, height)
