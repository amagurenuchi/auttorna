"""CLI for on-demand RF-DETR to ONNX export."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot.util.export_onnx import export_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a trusted RF-DETR checkpoint to ONNX")
    parser.add_argument("--weights", default="weights.pt")
    parser.add_argument("--output", default="model.onnx")
    parser.add_argument("--variant", choices=("nano", "small", "medium", "base", "large"), default="nano")
    parser.add_argument("--resolution", type=int, default=384)
    parser.add_argument("--patch-size", type=int, default=16)
    args = parser.parse_args()
    output = export_model(args.weights, args.output, args.variant, resolution=args.resolution, patch_size=args.patch_size)
    print(f"exported ONNX model: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
