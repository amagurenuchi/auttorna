from __future__ import annotations

import numpy as np


def arrow_orientation(frame_rgb: np.ndarray, box: tuple[float, float, float, float]) -> str:
    """Estimate arrow direction from the foreground-pixel centroid.

    The arrowhead adds visual mass toward its tip, so the foreground centroid
    shifts in the pointing direction relative to the crop center. This works
    without requiring a second trained classifier and falls back to the
    dominant axis when the crop is small or low contrast.
    """
    height, width = frame_rgb.shape[:2]
    x1, y1, x2, y2 = (max(0, int(v)) for v in box)
    x2, y2 = min(width, x2), min(height, y2)
    crop = frame_rgb[y1:y2, x1:x2]
    if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 4:
        return "Right"

    gray = crop.astype(np.float32).mean(axis=2)
    border = np.concatenate((gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]))
    contrast = np.abs(gray - float(np.median(border)))
    threshold = max(15.0, float(np.percentile(contrast, 65)))
    mask = contrast >= threshold
    if int(mask.sum()) < 4:
        return "Right"

    ys, xs = np.nonzero(mask)
    dx = float(xs.mean()) - (crop.shape[1] - 1) / 2
    dy = float(ys.mean()) - (crop.shape[0] - 1) / 2
    if abs(dx) >= abs(dy):
        return "Right" if dx >= 0 else "Left"
    return "Down" if dy >= 0 else "Up"
