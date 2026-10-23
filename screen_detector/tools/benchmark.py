from __future__ import annotations

import argparse
import time

import numpy as np

from ..inference.ort_backend import OnnxRuntimeDetector


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark a fixed-shape ONNX detector")
    parser.add_argument("model")
    parser.add_argument("--provider", default="auto")
    parser.add_argument("--resolution", type=int, default=576)
    parser.add_argument("--runs", type=int, default=100)
    args = parser.parse_args()
    detector = OnnxRuntimeDetector(args.model, [], provider=args.provider, resolution=args.resolution, warmup=True)
    frame = np.zeros((args.resolution, args.resolution, 3), dtype=np.uint8)
    samples = []
    for _ in range(args.runs):
        started = time.perf_counter_ns()
        detector.predict(frame)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    values = np.sort(np.asarray(samples))
    print({"provider": detector.provider, "runs": len(values), "p50_ms": float(np.percentile(values, 50)), "p95_ms": float(np.percentile(values, 95)), "p99_ms": float(np.percentile(values, 99))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
