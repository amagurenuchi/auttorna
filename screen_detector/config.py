from __future__ import annotations

import json
import argparse
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
    roi: tuple[int, int, int, int] | None = None
    lanes: list[tuple[int, int]] = field(default_factory=list)
    receptor_y: float | None = None
    scroll_speed_px_per_s: float | None = None
    display_refresh_hz: float | None = None
    global_offset_ms: float = 0.0
    inference_backend: str = "pytorch"
    input_backend: str = "sendinput"
    stall_timeout_ms: int = 250
    onnx_model: str = "model.onnx"
    lane_scancodes: dict[int, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        cap = raw.get("capture", {})
        inf = raw.get("inference", {})
        actions = raw.get("actions", {})
        roi_raw = raw.get("roi") or cap.get("roi")
        roi = tuple(int(value) for value in roi_raw) if roi_raw else None
        lanes = [tuple(int(value) for value in lane) for lane in raw.get("lanes", [])]
        return cls(
            weights=raw.get("weights", "weights.pt"), model_variant=raw.get("model_variant", "base"), patch_size=int(raw.get("patch_size", 16)),
            device=raw.get("device", "auto"), class_names=raw.get("class_names", []),
            confidence=float(raw.get("confidence", 0.55)), capture_source=cap.get("source", "monitor"),
            monitor=int(cap.get("monitor", 1)), window_title=cap.get("window_title", ""), capture_backend=cap.get("backend", "pillow"),
            max_fps=int(inf.get("max_fps", 20)), resolution=int(inf.get("resolution", 576)),
            actions_enabled=bool(actions.get("enabled", False)), activation_frames=int(actions.get("activation_frames", 2)),
            release_frames=int(actions.get("release_frames", 3)), cooldown_seconds=float(actions.get("cooldown_seconds", 0.15)),
            class_to_key=dict(actions.get("class_to_key", {})), action_keys=dict(actions.get("action_keys", {})), emergency_hotkey=raw.get("emergency_hotkey", "f12"),
            roi=roi, lanes=lanes, receptor_y=raw.get("receptor_y"),
            scroll_speed_px_per_s=raw.get("scroll_speed_px_per_s"), display_refresh_hz=raw.get("display_refresh_hz"),
            global_offset_ms=float(raw.get("global_offset_ms", 0.0)), inference_backend=raw.get("inference_backend", "pytorch"),
            input_backend=raw.get("input_backend", "sendinput"), stall_timeout_ms=int(raw.get("stall_timeout_ms", 250)),
            onnx_model=raw.get("onnx_model", "model.onnx"),
            lane_scancodes={int(key): int(value) for key, value in dict(raw.get("lane_scancodes", {})).items()},
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not Path(self.weights).is_file(): errors.append(f"Weights file not found: {self.weights}")
        if not 0 < self.confidence <= 1: errors.append("confidence must be between 0 and 1")
        if self.capture_source not in {"monitor", "window"}: errors.append("capture.source must be monitor or window")
        if self.capture_backend not in {"pillow", "mss", "dxcam", "wgc"}: errors.append("capture.backend must be pillow, mss, dxcam, or wgc")
        if self.capture_source == "window" and not self.window_title: errors.append("capture.window_title is required")
        if not self.class_names: errors.append("class_names is empty; add labels in training order")
        if self.activation_frames < 1 or self.release_frames < 1: errors.append("activation/release frames must be positive")
        if self.roi is not None and (len(self.roi) != 4 or self.roi[2] <= 0 or self.roi[3] <= 0): errors.append("roi must be [x, y, width, height] with positive dimensions")
        if any(len(lane) != 2 or lane[1] <= lane[0] for lane in self.lanes): errors.append("lanes must contain [left, right] bounds")
        if self.inference_backend not in {"pytorch", "onnxruntime", "directml", "openvino", "tensorrt", "cpu"}: errors.append("unsupported inference_backend")
        if self.input_backend != "sendinput": errors.append("input_backend must be sendinput on Windows")
        if any(lane < 0 or code <= 0 or code > 0xFF for lane, code in self.lane_scancodes.items()): errors.append("lane_scancodes must map non-negative lanes to scan codes 1..255")
        if self.stall_timeout_ms < 1: errors.append("stall_timeout_ms must be positive")
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
            "roi": list(self.roi) if self.roi else None,
            "lanes": [list(lane) for lane in self.lanes],
            "receptor_y": self.receptor_y,
            "scroll_speed_px_per_s": self.scroll_speed_px_per_s,
            "display_refresh_hz": self.display_refresh_hz,
            "global_offset_ms": self.global_offset_ms,
            "inference_backend": self.inference_backend,
            "input_backend": self.input_backend,
            "stall_timeout_ms": self.stall_timeout_ms,
            "onnx_model": self.onnx_model,
            "lane_scancodes": {str(lane): code for lane, code in self.lane_scancodes.items()},
        }
        Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Auttorna configuration and report the Windows environment")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--check", action="store_true", help="validate configuration and print the environment")
    args = parser.parse_args()
    settings = Settings.load(args.config)
    errors = settings.validate()
    from .environment import environment_summary, format_summary
    print(format_summary(environment_summary(settings.window_title)))
    if errors:
        print("configuration errors:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("configuration: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
