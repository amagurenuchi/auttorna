from __future__ import annotations

import ctypes
import time

from .debug import logger


class KeyboardController:
    _special = {
        "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "space": 0x20,
        "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
        ",": 0xBC, ".": 0xBE, "/": 0xBF, ";": 0xBA, "'": 0xDE,
        "[": 0xDB, "]": 0xDD, "\\": 0xDC, "-": 0xBD, "=": 0xBB,
        **{f"f{i}": 0x6F + i for i in range(1, 13)},
    }
    def __init__(self, mapping: dict[str, str], activation_frames: int, release_frames: int, cooldown: float) -> None:
        self.mapping, self.activation_frames, self.release_frames, self.cooldown = mapping, activation_frames, release_frames, cooldown
        self.states: dict[str, list[int | bool]] = {k: [0, 0, False] for k in mapping}; self.held: set[str] = set(); self.last = 0.0

    def _vk(self, key: str) -> int:
        k = key.lower()
        if k in self._special: return self._special[k]
        if len(k) == 1: return ord(k.upper())
        raise ValueError(f"Unsupported key mapping: {key}")

    def _send(self, key: str, up: bool) -> None:
        logger.info("input %s: %s", "key-up" if up else "key-down", key)
        if not hasattr(ctypes, "windll"): return
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
        # INPUT is a 40-byte structure on 64-bit Windows; declaring the union
        # explicitly keeps SendInput ABI-compatible on both 32/64-bit Python.
        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ki", KEYBDINPUT)]
        data = INPUT(); data.type = 1; data.ki.wVk = self._vk(key); data.ki.dwFlags = 2 if up else 0
        ctypes.windll.user32.SendInput(1, ctypes.byref(data), ctypes.sizeof(data))

    @classmethod
    def tap_key(cls, key: str) -> None:
        logger.info("testing input: %s", key)
        controller = cls({}, 1, 1, 0)
        controller._send(key, False)
        time.sleep(0.03)
        controller._send(key, True)

    def update(self, labels: set[str], enabled: bool) -> None:
        now = time.monotonic()
        for label, state in self.states.items():
            active = label in labels; active_count = int(state[0]); missing_count = int(state[1]); was = bool(state[2])
            active_count, missing_count = (min(active_count + 1, self.activation_frames), 0) if active else (0, missing_count + 1)
            if not was and active_count >= self.activation_frames and enabled and now - self.last >= self.cooldown:
                self._send(self.mapping[label], False); self.held.add(label); state[2] = True; self.last = now
            elif was and missing_count >= self.release_frames:
                self._send(self.mapping[label], True); self.held.discard(label); state[2] = False
            state[0] = active_count; state[1] = missing_count

    def release_all(self) -> None:
        for label in list(self.held): self._send(self.mapping[label], True)
        self.held.clear()
        for state in self.states.values(): state[:] = [0, 0, False]
