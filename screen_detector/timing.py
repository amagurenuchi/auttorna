from __future__ import annotations

import csv
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterator


@dataclass(frozen=True)
class TimingSample:
    stage: str
    started_ns: int
    ended_ns: int

    @property
    def duration_ns(self) -> int:
        return max(0, self.ended_ns - self.started_ns)


class TimingRecorder:
    """Bounded stage timing recorder suitable for the hot path."""

    def __init__(self, max_samples: int = 10_000) -> None:
        if max_samples < 1:
            raise ValueError("max_samples must be positive")
        self._samples: deque[TimingSample] = deque(maxlen=max_samples)
        self._lock = Lock()

    def record(self, stage: str, started_ns: int, ended_ns: int | None = None) -> None:
        ended_ns = time.perf_counter_ns() if ended_ns is None else ended_ns
        with self._lock:
            self._samples.append(TimingSample(stage, started_ns, ended_ns))

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.perf_counter_ns()
        try:
            yield
        finally:
            self.record(name, started)

    def samples(self, stage: str | None = None) -> list[TimingSample]:
        with self._lock:
            values = list(self._samples)
        return [sample for sample in values if stage is None or sample.stage == stage]

    def stats(self, stage: str) -> dict[str, float | int]:
        values = sorted(sample.duration_ns for sample in self.samples(stage))
        if not values:
            return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}

        def percentile(percent: float) -> float:
            index = (len(values) - 1) * percent
            lower, upper = int(index), min(int(index) + 1, len(values) - 1)
            return (values[lower] + (values[upper] - values[lower]) * (index - lower)) / 1_000_000

        return {"count": len(values), "p50_ms": percentile(0.50), "p95_ms": percentile(0.95), "p99_ms": percentile(0.99)}

    def all_stats(self) -> dict[str, dict[str, float | int]]:
        return {stage: self.stats(stage) for stage in sorted({sample.stage for sample in self.samples()})}

    def write_csv(self, path: str | Path) -> None:
        rows = self.samples()
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("stage", "started_ns", "ended_ns", "duration_ns"))
            writer.writerows((row.stage, row.started_ns, row.ended_ns, row.duration_ns) for row in rows)
