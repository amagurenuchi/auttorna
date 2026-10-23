from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from ..model import RFDetector


def export_model(weights: str, output: str, variant: str, labels: list[str], resolution: int, patch_size: int) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("RF-DETR's PyTorch installation is required for export") from exc
    detector = RFDetector(weights, variant, "cpu", labels, 0.01, patch_size, resolution)
    # RF-DETR exposes a ModelContext at detector.model.model; the actual
    # torch.nn.Module is one level deeper.
    wrapper = detector.model.model.model
    if wrapper is None:
        raise RuntimeError("RF-DETR did not expose its underlying model")
    wrapper.eval()
    if hasattr(wrapper, "export"):
        wrapper.export()
    dummy = torch.zeros((1, 3, detector.resolution, detector.resolution), dtype=torch.float32)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        wrapper,
        dummy,
        str(destination),
        input_names=["images"],
        opset_version=18,
        do_constant_folding=True,
    )
    print(f"exported fixed-shape ONNX model: {destination} ({detector.resolution}x{detector.resolution})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the trusted RF-DETR checkpoint to fixed-shape ONNX")
    parser.add_argument("--weights", default="weights.pt")
    parser.add_argument("--output", default="model.onnx")
    parser.add_argument("--variant", default="base")
    parser.add_argument("--labels", nargs="+", default=["arrow", "receptor"])
    parser.add_argument("--resolution", type=int, default=576)
    parser.add_argument("--patch-size", type=int, default=16)
    args = parser.parse_args()
    export_model(args.weights, args.output, args.variant, args.labels, args.resolution, args.patch_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
