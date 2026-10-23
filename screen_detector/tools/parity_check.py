from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from ..inference.ort_backend import OnnxRuntimeDetector
from ..model import RFDetector


def iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_first = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_second = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_first + area_second - intersection
    return intersection / union if union else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare PyTorch and ONNX detections on the same images")
    parser.add_argument("--weights", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--images", nargs="+", required=True)
    parser.add_argument("--labels", nargs="+", default=["arrow", "receptor"])
    parser.add_argument("--threshold", type=float, default=0.3)
    parser.add_argument("--resolution", type=int, default=576)
    args = parser.parse_args()
    torch_detector = RFDetector(args.weights, "base", "cpu", args.labels, args.threshold, resolution=args.resolution)
    ort_detector = OnnxRuntimeDetector(args.model, args.labels, args.threshold, args.resolution, "auto")
    total = matched = mismatches = 0
    for image_path in args.images:
        frame = np.asarray(Image.open(Path(image_path)).convert("RGB"))
        reference, candidate = torch_detector.predict(frame), ort_detector.predict(frame)
        total += len(reference)
        for expected in reference:
            matches = [item for item in candidate if item.class_id == expected.class_id]
            if matches and max(iou(expected.box, item.box) for item in matches) >= 0.5:
                matched += 1
        mismatches += abs(len(reference) - len(candidate))
    print({"images": len(args.images), "torch_detections": total, "iou_matched": matched, "count_mismatches": mismatches, "match_rate": matched / total if total else 1.0})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
