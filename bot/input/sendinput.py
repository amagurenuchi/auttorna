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
        user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
        user32.VkKeyScanW.restype = ctypes.c_short
        user32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
        user32.MapVirtualKeyW.restype = ctypes.c_uint
        vk = user32.VkKeyScanW(key[0]) & 0xFF if key else 0
        scan = user32.MapVirtualKeyW(vk, 0)
        if not scan:
            logger.error("could not map key to scan code: lane=%d key=%r vk=%d", col, key, vk)
            return

        ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", ULONG_PTR)]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort),
                        ("wParamH", ctypes.c_ushort)]

        class INPUTUNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            # INPUT contains a union; omitting the larger mouse member makes
            # sizeof(INPUT) 32 instead of the 40 bytes required on Win64.
            _fields_ = [("type", ctypes.c_ulong), ("data", INPUTUNION)]

        user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = ctypes.c_uint

        KEYEVENTF_SCANCODE = 0x0008
        KEYEVENTF_KEYUP = 0x0002
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if not down else 0)
        event = INPUT(1, INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)))
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
