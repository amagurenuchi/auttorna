from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class Detection:
    box: tuple[float, float, float, float]
    confidence: float
    class_id: int
    label: str


class RFDetector:
    def __init__(self, weights: str, variant: str, device: str, labels: list[str], threshold: float, patch_size: int = 16, resolution: int = 576) -> None:
        try:
            from rfdetr import RFDETRBase, RFDETRLarge, RFDETRMedium, RFDETRNano, RFDETRSmall
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: python -m pip install -r requirements.txt") from exc
        names = {"nano": RFDETRNano, "small": RFDETRSmall, "medium": RFDETRMedium, "base": RFDETRBase, "large": RFDETRLarge}
        if variant not in names: raise RuntimeError(f"Unsupported model_variant: {variant}")
        # This checkpoint has legacy metadata and cannot be resolved through
        # from_checkpoint(). Instantiate the selected architecture directly.
        # An absolute path is important because RF-DETR treats bare filenames
        # as entries in its model cache.
        kwargs = {"device": device} if device != "auto" else {}
        kwargs["pretrain_weights"] = str(Path(weights).resolve())
        kwargs["patch_size"] = patch_size
        if labels:
            kwargs["num_classes"] = len(labels)
        try:
            try:
                self.model = names[variant](trust_checkpoint=True, **kwargs)
            except TypeError as exc:
                if "trust_checkpoint" not in str(exc):
                    raise
                # Older RF-DETR releases do not expose trust_checkpoint on
                # the constructor, but still accept the same checkpoint path.
                self.model = names[variant](**kwargs)
        except Exception as exc:
            raise RuntimeError(f"Could not load RF-DETR checkpoint with variant '{variant}' directly: {exc}") from exc
        self.labels = labels
        self.threshold = threshold
        block_size = patch_size * 4
        self.resolution = ((resolution + block_size - 1) // block_size) * block_size
        checkpoint_classes = getattr(self.model, "class_names", None)
        if checkpoint_classes and not labels: self.labels = list(checkpoint_classes)

    def predict(self, frame_rgb: np.ndarray) -> list[Detection]:
        result: Any = self.model.predict(frame_rgb, threshold=self.threshold, shape=(self.resolution, self.resolution))
        ids = np.asarray(result.class_id).reshape(-1); boxes = np.asarray(result.xyxy); scores = np.asarray(result.confidence).reshape(-1)
        output = []
        for box, score, class_id in zip(boxes, scores, ids):
            cid = int(class_id); label = self.labels[cid] if 0 <= cid < len(self.labels) else str(cid)
            output.append(Detection(tuple(float(x) for x in box), float(score), cid, label))
        return output
