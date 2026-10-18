from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Settings:
    weights: str = "weights.pt"
    model_variant: str = "base"
    patch_size: int = 16
    device: str = "auto"
    class_names: list[str] = field(default_factory=list)
    confidence: float = 0.3
    capture_source: str = "monitor"
    capture_backend: str = "pillow"
    monitor: int = 1
    window_title: str = ""
    max_fps: int = 30
    resolution: int = 576
    actions_enabled: bool = False
    activation_frames: int = 2
    release_frames: int = 3
    cooldown_seconds: float = 0.15
    class_to_key: dict[str, str] = field(default_factory=dict)
    action_keys: dict[str, str] = field(default_factory=dict)
    emergency_hotkey: str = "f12"

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        cap = raw.get("capture", {})
        inf = raw.get("inference", {})
        actions = raw.get("actions", {})
        return cls(
            weights=raw.get("weights", "weights.pt"), model_variant=raw.get("model_variant", "base"), patch_size=int(raw.get("patch_size", 16)),
            device=raw.get("device", "auto"), class_names=raw.get("class_names", []),
            confidence=float(raw.get("confidence", 0.55)), capture_source=cap.get("source", "monitor"),
            monitor=int(cap.get("monitor", 1)), window_title=cap.get("window_title", ""), capture_backend=cap.get("backend", "pillow"),
            max_fps=int(inf.get("max_fps", 20)), resolution=int(inf.get("resolution", 576)),
            actions_enabled=bool(actions.get("enabled", False)), activation_frames=int(actions.get("activation_frames", 2)),
            release_frames=int(actions.get("release_frames", 3)), cooldown_seconds=float(actions.get("cooldown_seconds", 0.15)),
            class_to_key=dict(actions.get("class_to_key", {})), action_keys=dict(actions.get("action_keys", {})), emergency_hotkey=raw.get("emergency_hotkey", "f12"),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not Path(self.weights).is_file(): errors.append(f"Weights file not found: {self.weights}")
        if not 0 < self.confidence <= 1: errors.append("confidence must be between 0 and 1")
        if self.capture_source not in {"monitor", "window"}: errors.append("capture.source must be monitor or window")
        if self.capture_backend not in {"pillow", "mss"}: errors.append("capture.backend must be pillow or mss")
        if self.capture_source == "window" and not self.window_title: errors.append("capture.window_title is required")
        if not self.class_names: errors.append("class_names is empty; add labels in training order")
        if self.activation_frames < 1 or self.release_frames < 1: errors.append("activation/release frames must be positive")
        return errors

    def save(self, path: str | Path) -> None:
        payload = {
            "weights": self.weights,
            "model_variant": self.model_variant,
            "patch_size": self.patch_size,
            "device": self.device,
            "class_names": self.class_names,
            "confidence": self.confidence,
            "capture": {"source": self.capture_source, "backend": self.capture_backend, "monitor": self.monitor, "window_title": self.window_title},
            "inference": {"max_fps": self.max_fps, "resolution": self.resolution},
            "actions": {
                "enabled": self.actions_enabled,
                "activation_frames": self.activation_frames,
                "release_frames": self.release_frames,
                "cooldown_seconds": self.cooldown_seconds,
                "class_to_key": self.class_to_key,
                "action_keys": self.action_keys,
            },
            "emergency_hotkey": self.emergency_hotkey,
        }
        Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
