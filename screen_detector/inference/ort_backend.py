from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..model import Detection
from .preprocess import FixedPreprocessor


def available_providers() -> list[str]:
    try:
        import onnxruntime as ort
        return list(ort.get_available_providers())
    except ImportError:
        return []


def choose_provider(requested: str = "auto") -> str:
    providers = available_providers()
    preference = {
        "directml": "DmlExecutionProvider",
        "cuda": "CUDAExecutionProvider",
        "tensorrt": "TensorrtExecutionProvider",
        "openvino": "OpenVINOExecutionProvider",
        "cpu": "CPUExecutionProvider",
    }
    if requested != "auto":
        selected = preference.get(requested, requested)
        if selected not in providers:
            raise RuntimeError(f"Requested ONNX Runtime provider {selected!r} is unavailable; installed providers: {providers}")
        return selected
    for selected in ("DmlExecutionProvider", "CUDAExecutionProvider", "OpenVINOExecutionProvider", "CPUExecutionProvider"):
        if selected in providers:
            return selected
    raise RuntimeError(f"No usable ONNX Runtime providers are installed: {providers}")


class OnnxRuntimeDetector:
    def __init__(self, model_path: str, labels: list[str], threshold: float = 0.3, resolution: int = 576, provider: str = "auto", warmup: bool = True) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("Install ONNX Runtime with: python -m pip install onnxruntime-directml") from exc
        selected = choose_provider(provider)
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if selected == "DmlExecutionProvider":
            options.enable_mem_pattern = False
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(model_path, sess_options=options, providers=[selected, "CPUExecutionProvider"] if selected != "CPUExecutionProvider" else [selected])
        self.input_name = self.session.get_inputs()[0].name
        self.labels = labels
        self.threshold = float(threshold)
        self.preprocessor = FixedPreprocessor(resolution)
        self.provider = selected
        self.resolution = resolution
        if warmup:
            self.predict(np.zeros((resolution, resolution, 3), dtype=np.uint8))

    def predict(self, frame_rgb: np.ndarray) -> list[Detection]:
        prepared = self.preprocessor(frame_rgb)
        outputs = self.session.run(None, {self.input_name: prepared.tensor})
        return self._decode(outputs, prepared.source_width, prepared.source_height)

    def _decode(self, outputs: list[Any], source_width: int, source_height: int) -> list[Detection]:
        arrays = [np.asarray(output) for output in outputs]
        box_index = next((index for index, array in enumerate(arrays) if array.ndim >= 2 and array.shape[-1] == 4), None)
        boxes = arrays[box_index] if box_index is not None else None
        if boxes is None:
            raise RuntimeError("ONNX output does not contain a [..., 4] box tensor")
        boxes = boxes.reshape(-1, 4)
        remaining = [array.reshape(-1) for index, array in enumerate(arrays) if index != box_index]
        scores: np.ndarray | None = None
        class_ids: np.ndarray | None = None
        for array in remaining:
            if array.size != boxes.shape[0]:
                continue
            if np.issubdtype(array.dtype, np.integer):
                class_ids = array.astype(np.int64)
            elif scores is None:
                scores = array.astype(np.float32)
        if scores is None:
            logits = next((array for index, array in enumerate(arrays) if index != box_index and array.ndim >= 2 and array.shape[-1] != 4 and array.size // boxes.shape[0] == array.shape[-1]), None)
            if logits is None:
                raise RuntimeError("ONNX output does not contain scores or logits matching the boxes")
            logits = logits.reshape(boxes.shape[0], -1).astype(np.float32)
            probabilities = 1 / (1 + np.exp(-logits))
            class_ids = probabilities.argmax(axis=1)
            scores = probabilities.max(axis=1)
        if class_ids is None:
            class_ids = np.zeros(boxes.shape[0], dtype=np.int64)
        output: list[Detection] = []
        for box, score, class_id in zip(boxes, scores, class_ids):
            confidence = float(score)
            if not math.isfinite(confidence) or confidence < self.threshold:
                continue
            x1, y1, x2, y2 = (float(value) for value in box)
            if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
                x1, x2 = x1 * source_width, x2 * source_width
                y1, y2 = y1 * source_height, y2 * source_height
            else:
                x1, x2 = x1 * source_width / self.resolution, x2 * source_width / self.resolution
                y1, y2 = y1 * source_height / self.resolution, y2 * source_height / self.resolution
            cid = int(class_id)
            label = self.labels[cid] if 0 <= cid < len(self.labels) else str(cid)
            output.append(Detection((x1, y1, x2, y2), confidence, cid, label))
        return output
