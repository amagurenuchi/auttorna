"""Small screenshot-based Tkinter pickers for ROI and receptor calibration."""

from __future__ import annotations

import base64
from collections.abc import Callable
from io import BytesIO
import tkinter as tk


def _screen_rgb() -> tuple[int, int, bytes]:
    """Capture the primary monitor and return width, height, RGB bytes."""
    try:
        import mss
        with mss.mss() as capture:
            monitor = capture.monitors[1]
            shot = capture.grab(monitor)
            return shot.width, shot.height, shot.rgb
    except ImportError as error:
        raise RuntimeError("Install the Windows capture extras before using visual pickers") from error


def _photo_image(parent: tk.Misc, width: int, height: int, rgb: bytes) -> tk.PhotoImage:
    """Encode RGB pixels as PNG, which is reliably decoded by Tk 8.6+."""
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Install Pillow before using the visual pickers") from error
    output = BytesIO()
    Image.frombytes("RGB", (width, height), rgb).save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return tk.PhotoImage(master=parent, data=encoded, format="PNG")


def pick_roi(parent: tk.Misc, callback: Callable[[tuple[int, int, int, int]], None]) -> None:
    """Show a screen overlay and return a rectangle in screen coordinates."""
    width, height, rgb = _screen_rgb()
    window = tk.Toplevel(parent)
    window.title("Select playfield ROI")
    window.attributes("-topmost", True)
    window.geometry(f"{width}x{height}+0+0")
    window.overrideredirect(True)
    image = _photo_image(window, width, height, rgb)
    canvas = tk.Canvas(window, width=width, height=height, cursor="crosshair", highlightthickness=0)
    canvas.pack()
    # Tk does not retain a Python reference to images created for a widget.
    # Keep it attached to the canvas or the overlay becomes blank/white as
    # soon as this function returns.
    canvas.image = image
    canvas.create_image(0, 0, image=image, anchor="nw")
    canvas.create_text(12, 12, text="Drag around the playfield; Esc cancels", anchor="nw", fill="yellow", font=("Segoe UI", 14, "bold"))
    start: list[int] = []
    rectangle: list[int] = []

    def begin(event: tk.Event) -> None:
        start[:] = [event.x, event.y]
        if rectangle:
            canvas.delete(rectangle[0])
        rectangle[:] = [canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="lime", width=3)]

    def move(event: tk.Event) -> None:
        if start and rectangle:
            canvas.coords(rectangle[0], start[0], start[1], event.x, event.y)

    def finish(event: tk.Event) -> None:
        if not start:
            return
        left, right = sorted((start[0], event.x))
        top, bottom = sorted((start[1], event.y))
        if right - left > 10 and bottom - top > 10:
            callback((left, top, right, bottom))
            window.destroy()

    canvas.bind("<ButtonPress-1>", begin)
    canvas.bind("<B1-Motion>", move)
    canvas.bind("<ButtonRelease-1>", finish)
    window.bind("<Escape>", lambda _event: window.destroy())
    window.focus_force()


def pick_receptor(parent: tk.Misc, roi: tuple[int, int, int, int], callback: Callable[[int], None]) -> None:
    """Show the ROI and return a receptor Y coordinate relative to that ROI."""
    left, top, right, bottom = roi
    width, height, rgb = _screen_rgb()
    crop_width, crop_height = right - left, bottom - top
    if left < 0 or top < 0 or right > width or bottom > height or crop_width <= 0 or crop_height <= 0:
        raise ValueError("ROI is outside the primary monitor or has invalid dimensions")
    cropped = bytearray()
    for y in range(top, bottom):
        start = (y * width + left) * 3
        cropped.extend(rgb[start:start + crop_width * 3])
    window = tk.Toplevel(parent)
    window.title("Click receptor line")
    window.attributes("-topmost", True)
    image = _photo_image(window, crop_width, crop_height, bytes(cropped))
    canvas = tk.Canvas(window, width=crop_width, height=crop_height, cursor="crosshair", highlightthickness=0)
    canvas.pack()
    canvas.image = image
    canvas.create_image(0, 0, image=image, anchor="nw")
    canvas.create_text(12, 12, text="Click the center of the receptor arrows; Esc cancels", anchor="nw", fill="yellow", font=("Segoe UI", 12, "bold"))
    canvas.bind("<Button-1>", lambda event: (callback(int(event.y)), window.destroy()))
    window.bind("<Escape>", lambda _event: window.destroy())
    window.focus_force()
