"""ONNX Runtime detector wrapper with a deliberately small adapter surface."""

from typing import Protocol
import math

from bot.model import Detection


class Detector(Protocol):
    def detect(self, frame: object, captured_at: float) -> list[Detection]: ...


class OnnxDetector:
    def __init__(self, model_path: str, classes: list[str], threshold: float = 0.5,
                 input_size: int = 384, provider: str = "auto") -> None:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        preferred = {"directml": "DmlExecutionProvider", "cuda": "CUDAExecutionProvider"}.get(provider)
        selected = [preferred] if preferred in providers else []
        selected.append("CPUExecutionProvider")
        self.session = ort.InferenceSession(model_path, providers=selected)
        self.classes, self.threshold, self.input_size = classes, threshold, input_size

    def detect(self, frame: object, captured_at: float) -> list[Detection]:
        # Model-specific postprocessing is kept here so the rest of the pipeline
        # only consumes stable Detection values. RF-DETR exports are accepted as
        # [x1,y1,x2,y2,score,class] rows or a matching tuple of arrays.
        import numpy as np
        image = np.asarray(frame)
        if image.ndim != 3:
            raise ValueError(f"capture frame must be HxWxC, got shape={image.shape}")
        original_height, original_width = image.shape[:2]
        if image.shape[2] == 4:
            image = image[:, :, :3]
        if image.shape[2] != 3:
            raise ValueError(f"capture frame must have 3 or 4 channels, got shape={image.shape}")
        from PIL import Image
        resized = Image.fromarray(image.astype("uint8"), mode="RGB").resize((self.input_size, self.input_size), Image.Resampling.BILINEAR)
        model_image = np.asarray(resized, dtype="float32")
        model_image = model_image[None].transpose(0, 3, 1, 2) / 255.0
        scale_x = original_width / self.input_size
        scale_y = original_height / self.input_size
        output = [np.asarray(value) for value in self.session.run(None, {self.session.get_inputs()[0].name: model_image})]
        box_index = next((index for index, value in enumerate(output) if value.ndim >= 2 and value.shape[-1] == 4), None)
        if box_index is None:
            raise RuntimeError(f"ONNX output does not contain a box tensor: {[value.shape for value in output]}")
        boxes = output[box_index].reshape(-1, 4)
        logits = next((value for index, value in enumerate(output) if index != box_index and value.ndim >= 2 and value.size // boxes.shape[0] == value.shape[-1]), None)
        if logits is None:
            raise RuntimeError(f"ONNX output does not contain class logits: {[value.shape for value in output]}")
        logits = logits.reshape(boxes.shape[0], -1).astype("float32")
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        class_ids = probabilities.argmax(axis=1)
        scores = probabilities.max(axis=1)
        result = []
        for box, score, class_id in zip(boxes, scores, class_ids):
            score = float(score)
            if not math.isfinite(score) or score < self.threshold:
                continue
            center_x, center_y, box_width, box_height = (float(value) for value in box)
            if max(abs(center_x), abs(center_y), abs(box_width), abs(box_height)) <= 1.5:
                center_x *= original_width
                center_y *= original_height
                box_width *= original_width
                box_height *= original_height
            else:
                center_x *= scale_x
                center_y *= scale_y
                box_width *= scale_x
                box_height *= scale_y
            x1 = center_x - box_width / 2
            y1 = center_y - box_height / 2
            x2 = center_x + box_width / 2
            y2 = center_y + box_height / 2
            col = int(max(0, min(3, round(((x1 + x2) / 2) / max(1, original_width) * 4 - 0.5))))
            label = self.classes[int(class_id)] if int(class_id) < len(self.classes) else str(int(class_id))
            result.append(Detection(captured_at, col, (y1 + y2) / 2, label, score))
        return result
