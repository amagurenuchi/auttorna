from __future__ import annotations

import ctypes
import importlib.util
import os
import platform
import subprocess
from typing import Any


def _gpu_info() -> list[str]:
    if os.name != "nt":
        return []
    command = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _providers() -> list[str]:
    if importlib.util.find_spec("onnxruntime") is None:
        return []
    try:
        import onnxruntime
        return list(onnxruntime.get_available_providers())
    except Exception:
        return []


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def environment_summary(window_title: str = "") -> dict[str, Any]:
    summary: dict[str, Any] = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "gpu": _gpu_info(),
        "onnxruntime_providers": _providers(),
        "elevated": is_elevated(),
        "display": [],
    }
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            summary["display"] = [{"width": user32.GetSystemMetrics(0), "height": user32.GetSystemMetrics(1)}]
        except (AttributeError, OSError):
            pass
    if window_title:
        from .capture import windows
        titles = windows()
        summary["target_window"] = {"title": window_title, "found": any(window_title.lower() in title.lower() for title in titles)}
    return summary


def format_summary(summary: dict[str, Any]) -> str:
    lines = []
    for key, value in summary.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)
