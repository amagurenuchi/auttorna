from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from typing import Protocol

from ..debug import logger


class InputBackend(Protocol):
    def press(self, lane: int, action: str | int | None = None) -> int: ...
    def release(self, lane: int, action: str | int | None = None) -> int: ...
    def release_all(self) -> None: ...


@dataclass(frozen=True)
class InputEvent:
    lane: int
    scan_code: int
    key_up: bool


class SendInputBackend:
    """Windows scan-code SendInput backend.

    `lane_scancodes` must contain hardware scan codes, not virtual-key codes.
    `action` may be a configured lane name or a numeric scan code for tests and
    advanced callers.
    """

    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    def __init__(self, lane_scancodes: dict[int | str, int], enabled: bool = True) -> None:
        self.lane_scancodes = {key: int(value) for key, value in lane_scancodes.items()}
        self.enabled = enabled
        self.held: set[int] = set()

    def _scan_code(self, lane: int, action: str | int | None) -> int:
        candidates = (action, lane) if action is not None else (lane,)
        for candidate in candidates:
            if candidate in self.lane_scancodes:
                return self.lane_scancodes[candidate]
            if isinstance(candidate, str) and candidate.isdigit() and int(candidate) in self.lane_scancodes:
                return self.lane_scancodes[int(candidate)]
        raise ValueError(f"No scan code configured for lane {lane!r} / action {action!r}")

    def send_batch(self, events: list[InputEvent]) -> int:
        if not events:
            return 0
        if os.name != "nt" or not self.enabled:
            for event in events:
                (self.held.discard(event.lane) if event.key_up else self.held.add(event.lane))
            return 0
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ki", KEYBDINPUT)]
        inputs = (INPUT * len(events))()
        for index, event in enumerate(events):
            inputs[index].type = 1
            inputs[index].ki.wScan = event.scan_code
            inputs[index].ki.dwFlags = self.KEYEVENTF_SCANCODE | (self.KEYEVENTF_KEYUP if event.key_up else 0)
        sent = ctypes.windll.user32.SendInput(len(events), inputs, ctypes.sizeof(INPUT))
        if sent != len(events):
            raise OSError(f"SendInput sent {sent} of {len(events)} events")
        for event in events:
            (self.held.discard(event.lane) if event.key_up else self.held.add(event.lane))
        return int(sent)

    def send_actions(self, actions: list[tuple[int, str | int | None, str]]) -> int:
        events = []
        for lane, action, kind in actions:
            events.append(InputEvent(lane, self._scan_code(lane, action), kind == "release"))
        return self.send_batch(events)

    def press(self, lane: int, action: str | int | None = None) -> int:
        scan_code = self._scan_code(lane, action)
        logger.debug("scan-code press lane=%s code=%s", lane, scan_code)
        return self.send_batch([InputEvent(lane, scan_code, False)])

    def release(self, lane: int, action: str | int | None = None) -> int:
        scan_code = self._scan_code(lane, action)
        logger.debug("scan-code release lane=%s code=%s", lane, scan_code)
        return self.send_batch([InputEvent(lane, scan_code, True)])

    def release_all(self) -> None:
        for lane in list(self.held):
            try:
                self.release(lane)
            except (OSError, ValueError):
                logger.exception("failed to release lane %s", lane)
        self.held.clear()
