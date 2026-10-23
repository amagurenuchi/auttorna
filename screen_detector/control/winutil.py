from __future__ import annotations

import ctypes
import os


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def configure_process_priority() -> bool:
    """Request HIGH priority; never request REALTIME priority."""
    if os.name != "nt":
        return False
    try:
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        return bool(ctypes.windll.kernel32.SetPriorityClass(handle, 0x00000080))  # HIGH_PRIORITY_CLASS
    except (AttributeError, OSError):
        return False
