"""ONNX Runtime detector wrapper with a deliberately small adapter surface."""

from typing import Protocol

import numpy as np

from bot.model import Detection


class Detector(Protocol):
    def detect(self, frame: object, captured_at: float) -> list[Detection]: ...


class OnnxDetector:
    def __init__(self, model_path: str, classes: list[str], threshold: float = 0.5,
                 input_size: int = 384, provider: str = "auto") -> None:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if provider == "auto":
            preferred_providers = ("CUDAExecutionProvider", "DmlExecutionProvider")
        else:
            preferred_providers = ({"directml": "DmlExecutionProvider", "cuda": "CUDAExecutionProvider"}.get(provider),)
        selected = [candidate for candidate in preferred_providers if candidate in providers]
        if "CPUExecutionProvider" in providers:
            selected.append("CPUExecutionProvider")
        if not selected:
            raise RuntimeError(f"onnxruntime has no usable execution provider (available: {providers})")
        options = ort.SessionOptions()
        # The exported model has a fixed input shape, so ORT can safely fold
        # and fuse the graph once at load time. This is especially noticeable
        # on CPU, where otherwise small operators add up on every frame.
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, sess_options=options, providers=selected)
        self.classes, self.threshold, self.input_size = classes, threshold, input_size
        self._input_name = self.session.get_inputs()[0].name
        self._output_names = [output.name for output in self.session.get_outputs()]
        self._model_image = None
        self._mean = np.asarray((0.485, 0.456, 0.406), dtype="float32").reshape(1, 3, 1, 1)
        self._std = np.asarray((0.229, 0.224, 0.225), dtype="float32").reshape(1, 3, 1, 1)

    def detect(self, frame: object, captured_at: float) -> list[Detection]:
        # Model-specific postprocessing is kept here so the rest of the pipeline
        # only consumes stable Detection values. RF-DETR exports are accepted as
        # [x1,y1,x2,y2,score,class] rows or a matching tuple of arrays.
        image = np.asarray(frame)
        if image.ndim != 3:
            raise ValueError(f"capture frame must be HxWxC, got shape={image.shape}")
        original_height, original_width = image.shape[:2]
        if image.shape[2] == 4:
            image = image[:, :, :3]
        if image.shape[2] != 3:
            raise ValueError(f"capture frame must have 3 or 4 channels, got shape={image.shape}")
        if image.dtype != np.uint8 or not image.flags.c_contiguous:
            image = np.ascontiguousarray(image, dtype=np.uint8)
        from PIL import Image
        resized = Image.fromarray(image, mode="RGB").resize((self.input_size, self.input_size), Image.Resampling.BILINEAR)
        resized_array = np.asarray(resized, dtype="uint8")
        # Reuse the tensor buffer. The previous implementation created an
        # intermediate float HWC array, a transposed view, and another array
        # for each normalization operation on every captured frame.
        if self._model_image is None:
            self._model_image = np.empty((1, 3, self.input_size, self.input_size), dtype="float32")
        model_image = self._model_image
        model_image[0] = resized_array.transpose(2, 0, 1)
        model_image *= 1.0 / 255.0
        # RF-DETR's exported backbone expects the same ImageNet normalization
        # used by its native inference pipeline.
        model_image -= self._mean
        model_image /= self._std
        scale_x = original_width / self.input_size
        scale_y = original_height / self.input_size
        output = self.session.run(self._output_names, {self._input_name: model_image})
        box_index = next((index for index, value in enumerate(output) if value.ndim >= 2 and value.shape[-1] == 4), None)
        if box_index is None:
            raise RuntimeError(f"ONNX output does not contain a box tensor: {[value.shape for value in output]}")
        boxes = output[box_index].reshape(-1, 4)
        logits = next((value for index, value in enumerate(output) if index != box_index and value.ndim >= 2 and value.size // boxes.shape[0] == value.shape[-1]), None)
        if logits is None:
            raise RuntimeError(f"ONNX output does not contain class logits: {[value.shape for value in output]}")
        logits = logits.reshape(boxes.shape[0], -1).astype("float32")
        # RF-DETR exports one extra no-object logit after the foreground
        # classes. Never expose that logit as a detector label.
        foreground_logits = logits[:, :len(self.classes)]
        probabilities = 1.0 / (1.0 + np.exp(-foreground_logits))
        class_ids = probabilities.argmax(axis=1)
        scores = probabilities.max(axis=1)
        keep = np.isfinite(scores) & (scores >= self.threshold)
        if not np.any(keep):
            return []

        boxes = boxes[keep].astype("float32", copy=True)
        scores = scores[keep]
        class_ids = class_ids[keep]
        normalized = np.max(np.abs(boxes), axis=1) <= 1.5
        scale = np.where(
            normalized[:, None],
            np.asarray((original_width, original_height, original_width, original_height), dtype="float32"),
            np.asarray((scale_x, scale_y, scale_x, scale_y), dtype="float32"),
        )
        boxes *= scale
        centers_x = (boxes[:, 0] + boxes[:, 2]) / 2
        centers_y = (boxes[:, 1] + boxes[:, 3]) / 2
        columns = np.clip(np.rint(centers_x / max(1, original_width) * 4 - 0.5), 0, 3).astype("int32")

        # Only the small set of detections above threshold crosses the Python
        # boundary; the 300-query filtering and coordinate math stay in NumPy.
        result = []
        for center_y, col, score, class_id in zip(centers_y, columns, scores, class_ids):
            class_id = int(class_id)
            label = self.classes[class_id] if class_id < len(self.classes) else str(class_id)
            result.append(Detection(captured_at, int(col), float(center_y), label, float(score)))
        return result
