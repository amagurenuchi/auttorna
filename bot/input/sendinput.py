"""Windows SendInput adapter; importing it is safe on non-Windows hosts."""

import sys
import logging
import ctypes

logger = logging.getLogger(__name__)


class SendInput:
    def __init__(self, keymap: dict[int, str]) -> None:
        self.keymap = keymap
        self.held: set[int] = set()

    def __call__(self, col: int, down: bool) -> None:
        if sys.platform != "win32":
            logger.warning("input suppressed on non-Windows platform: col=%d down=%s", col, down)
            return
        key = self.keymap.get(col)
        if not key:
            if down:
                logger.warning("no key mapping for lane %d", col)
            return
        if not down and col not in self.held:
            return
        if sys.platform != "win32":
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        vk = user32.VkKeyScanW(key[0]) & 0xFF if key else 0
        scan = user32.MapVirtualKeyW(vk, 0)

        ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", ULONG_PTR)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ki", KEYBDINPUT)]

        user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = ctypes.c_uint
        user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
        user32.VkKeyScanW.restype = ctypes.c_short
        user32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
        user32.MapVirtualKeyW.restype = ctypes.c_uint

        KEYEVENTF_SCANCODE = 0x0008
        KEYEVENTF_KEYUP = 0x0002
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if not down else 0)
        event = INPUT(1, KEYBDINPUT(0, scan, flags, 0, 0))
        sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            logger.error("SendInput failed: lane=%d key=%r action=%s result=%d winerror=%d", col, key, "down" if down else "up", sent, ctypes.get_last_error())
            return
        logger.info("input sent: lane=%d key=%r scan=%d action=%s", col, key, scan, "down" if down else "up")
        if down:
            self.held.add(col)
        else:
            self.held.discard(col)

    def release_all(self) -> None:
        for col in tuple(self.held):
            self(col, False)
