"""Typed loading for the small YAML configuration surface."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    """Validated top-level settings needed by the application skeleton."""

    target_hz: int
    input_size: int
    chart_rate: float


def load_config(path: str | Path) -> AppConfig:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    vision = raw.get("vision", {})
    chart = raw.get("chart", {})
    target_hz = int(vision.get("target_hz", 20))
    input_size = int(vision.get("input_size", 384))
    chart_rate = float(chart.get("rate", 1.0))
    if target_hz <= 0 or input_size <= 0 or chart_rate <= 0:
        raise ValueError("target_hz, input_size, and chart.rate must be positive")
    return AppConfig(target_hz, input_size, chart_rate)
