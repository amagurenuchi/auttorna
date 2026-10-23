from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from .capture import create_capture, windows
from .config import Settings
from .debug import logger
from .keyboard import KeyboardController
from .model import RFDetector
from .orientation import arrow_orientation
from .pipeline import VisionPipeline
from .control.scheduler import Scheduler
from .timing import TimingRecorder


class App:
    ACTIONS = ("Left", "Down", "Up", "Right")

    def __init__(self, config_path: str = "config.json") -> None:
        self.config_path = Path(config_path)
        self.settings = Settings.load(self.config_path); self.root = tk.Tk(); self.root.title("Auttorna PoC")
        self.preview = ttk.Label(self.root); self.preview.pack(padx=8, pady=8); self.status = tk.StringVar(value="Stopped")
        bar = ttk.Frame(self.root); bar.pack(fill="x", padx=8)
        self.start_button = ttk.Button(bar, text="Start", command=self.start); self.start_button.pack(side="left")
        ttk.Button(bar, text="Stop", command=self.stop).pack(side="left", padx=4)
        ttk.Label(bar, text="Source").pack(side="left", padx=(12, 2))
        self.source = tk.StringVar(value="Window" if self.settings.capture_source == "window" else "Monitor")
        ttk.Combobox(bar, textvariable=self.source, values=("Monitor", "Window"), state="readonly", width=9).pack(side="left")
        ttk.Label(bar, text="Monitor").pack(side="left", padx=(8, 2))
        self.monitor = tk.IntVar(value=self.settings.monitor); ttk.Spinbox(bar, from_=1, to=16, width=3, textvariable=self.monitor).pack(side="left")
        ttk.Label(bar, text="Window").pack(side="left", padx=(8, 2))
        self.window_title = tk.StringVar(value=self.settings.window_title)
        self.window_list = ttk.Combobox(bar, textvariable=self.window_title, values=windows(), width=24)
        self.window_list.pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh_windows).pack(side="left", padx=2)
        ttk.Label(bar, text="Confidence").pack(side="left", padx=(8, 2))
        self.confidence = tk.DoubleVar(value=self.settings.confidence); ttk.Spinbox(bar, from_=0.05, to=1.0, increment=0.05, width=5, textvariable=self.confidence).pack(side="left")
        self.keyboard_enabled = False; self.key_vars: dict[str, tk.StringVar] = {}; self.key_buttons: dict[str, ttk.Button] = {}; self.capturing_label: str | None = None
        self.action_vars: dict[str, tk.StringVar] = {}
        self.input_panel = ttk.LabelFrame(self.root, text="Input configuration")
        self.input_panel.pack(fill="x", padx=8, pady=(4, 0))
        for row, action in enumerate(self.ACTIONS):
            ttk.Label(self.input_panel, text=action, width=10).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            value = tk.StringVar(value=self.settings.action_keys.get(action, "")); self.action_vars[action] = value
            ttk.Label(self.input_panel, textvariable=value, width=12, relief="sunken", anchor="center").grid(row=row, column=1, sticky="w", padx=6, pady=2)
            button = ttk.Button(self.input_panel, text="Set key", command=lambda name=action: self.begin_key_capture(name))
            button.grid(row=row, column=2, padx=2, pady=2); self.key_buttons[action] = button
            ttk.Button(self.input_panel, text="Clear", command=lambda name=action: self.clear_key(name)).grid(row=row, column=3, padx=2, pady=2)
            ttk.Button(self.input_panel, text="Test", command=lambda name=action: self.test_action(name)).grid(row=row, column=4, padx=2, pady=2)
        controls = ttk.Frame(self.input_panel); controls.grid(row=len(self.ACTIONS), column=0, columnspan=5, sticky="w", padx=4, pady=4)
        ttk.Button(controls, text="Apply mappings", command=self.apply_input_config).pack(side="left")
        self.input_button = ttk.Button(controls, text="Arm input", command=self.toggle_input); self.input_button.pack(side="left", padx=6)
        self.input_status = tk.StringVar(value="Input disarmed"); ttk.Label(controls, textvariable=self.input_status).pack(side="left")
        ttk.Label(self.root, textvariable=self.status).pack(pady=4)
        self.predictive_dry_run = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.root,
            text="Predictive tap dry-run (log only)",
            variable=self.predictive_dry_run,
        ).pack(anchor="w", padx=8)
        self.running = False; self.worker: threading.Thread | None = None; self.frames: queue.Queue = queue.Queue(maxsize=1); self.controller = None; self.scheduler = None
        self.timing = TimingRecorder()
        self.root.bind_all("<F12>", lambda _event: self.emergency_stop())
        self.root.protocol("WM_DELETE_WINDOW", self.close); self.root.after(40, self.render)

    def start(self) -> None:
        if not self.apply_input_config(): return
        self.settings.capture_source = "window" if self.source.get() == "Window" else "monitor"
        self.settings.monitor = int(self.monitor.get()); self.settings.confidence = float(self.confidence.get())
        self.settings.window_title = self.window_title.get().strip()
        errors = self.settings.validate()
        if errors: messagebox.showerror("Configuration", "\n".join(errors)); return
        logger.info("starting detection: source=%s monitor=%s window=%r confidence=%.2f", self.settings.capture_source, self.settings.monitor, self.settings.window_title, self.settings.confidence)
        self.running = True; self.start_button.configure(state="disabled"); self.worker = threading.Thread(target=self.loop, daemon=True); self.worker.start()

    def loop(self) -> None:
        try:
            if self.settings.inference_backend == "pytorch":
                detector = RFDetector(self.settings.weights, self.settings.model_variant, self.settings.device, self.settings.class_names, self.settings.confidence, self.settings.patch_size, self.settings.resolution)
            else:
                from .inference import OnnxRuntimeDetector
                provider = "directml" if self.settings.inference_backend == "directml" else self.settings.inference_backend
                detector = OnnxRuntimeDetector(self.settings.onnx_model, self.settings.class_names, self.settings.confidence, self.settings.resolution, provider)
            capture = create_capture(self.settings)
            keyboard = KeyboardController(self.settings.class_to_key, self.settings.activation_frames, self.settings.release_frames, self.settings.cooldown_seconds)
            self.controller = keyboard
            predictive = VisionPipeline(
                self.settings.lanes,
                self.settings.receptor_y,
                self.settings.scroll_speed_px_per_s,
                global_offset_ms=self.settings.global_offset_ms,
                timing=self.timing,
            ) if self.predictive_dry_run.get() and self.settings.lanes else None
            dry_backend = None
            if predictive is not None:
                from .pipeline import DryRunBackend
                dry_backend = DryRunBackend()
                self.scheduler = Scheduler(dry_backend, stale_timeout_ms=self.settings.stall_timeout_ms)
                self.scheduler.start()
                self.scheduler.arm()
            overlap_actions: set[tuple[int, int, str]] = set()
            last_detection_log = 0.0
            last_prediction_log = 0.0
            delay = 1 / max(1, self.settings.max_fps)
            while self.running:
                if self._f12_pressed():
                    self.running = False
                    keyboard.release_all()
                    break
                started = time.monotonic()
                with self.timing.stage("capture"):
                    captured = capture.read()
                if self.scheduler is not None:
                    self.scheduler.mark_frame(captured.captured_at_ns)
                frame = captured.frame
                with self.timing.stage("inference"):
                    detections = detector.predict(frame)
                predictions = predictive.update(detections, captured.captured_at_ns) if predictive is not None else []
                if self.scheduler is not None:
                    for event in predictions:
                        self.scheduler.schedule(event.target_ns, event.lane, note_id=event.note_id)
                if started - last_detection_log >= 1.0:
                    summary = ", ".join(f"{d.label}:{d.confidence:.2f}" for d in detections) or "none"
                    logger.info("detections=%d [%s]", len(detections), summary)
                    last_detection_log = started
                if predictions and started - last_prediction_log >= 0.25:
                    summary = ", ".join(
                        f"note={event.note_id} lane={event.lane} target={event.target_ns}"
                        for event in predictions
                    )
                    logger.info("predictive dry-run: %s", summary)
                    last_prediction_log = started
                current_actions: set[tuple[int, int, str]] = set()
                arrows = [d for d in detections if d.label.lower() == "arrow"]
                receptors = [d for d in detections if d.label.lower() == "receptor"]
                if self.keyboard_enabled:
                    for arrow_index, arrow in enumerate(arrows):
                        for receptor_index, receptor in enumerate(receptors):
                            if self._overlaps(arrow.box, receptor.box):
                                with self.timing.stage("orientation"):
                                    direction = arrow_orientation(frame, arrow.box)
                                event = (arrow_index, receptor_index, direction)
                                current_actions.add(event)
                                if event not in overlap_actions:
                                    key = self.settings.action_keys.get(direction, "")
                                    logger.info("arrow/receptor overlap: direction=%s key=%r", direction, key)
                                    if key:
                                        with self.timing.stage("input"):
                                            KeyboardController.tap_key(key)
                overlap_actions = current_actions
                image = Image.fromarray(frame); draw = ImageDraw.Draw(image)
                for d in detections:
                    draw.rectangle(d.box, outline="lime", width=3); draw.text((d.box[0], d.box[1]), f"{d.label} {d.confidence:.2f}", fill="yellow")
                image.thumbnail((960, 640));
                try: self.frames.put_nowait((image.copy(), len(detections), 1 / max(0.001, time.monotonic() - started)))
                except queue.Full: pass
                time.sleep(max(0, delay - (time.monotonic() - started)))
            if self.scheduler is not None:
                self.scheduler.stop()
                self.scheduler = None
            keyboard.release_all(); capture.close()
        except Exception as exc:
            logger.exception("detection stopped because of an error: %s", exc)
            if self.scheduler is not None:
                self.scheduler.stop()
                self.scheduler = None
            self.frames.put((None, 0, 0, str(exc))); self.running = False

    def render(self) -> None:
        try:
            item = self.frames.get_nowait()
            if item[0] is None: self.status.set(f"Error: {item[3]}")
            else:
                image, count, fps = item
                photo = ImageTk.PhotoImage(image)
                self.preview.configure(image=photo); self.preview.image = photo
                self.status.set(f"Running | {count} detections | {fps:.1f} FPS")
        except queue.Empty: pass
        self.root.after(40, self.render)

    def stop(self) -> None:
        self.running = False; self.keyboard_enabled = False
        if self.scheduler is not None:
            self.scheduler.stop(); self.scheduler = None
        if self.controller is not None: self.controller.release_all()
        self.input_button.configure(text="Arm input"); self.start_button.configure(state="normal"); self.status.set("Stopped")

    def refresh_windows(self) -> None:
        titles = windows()
        self.window_list.configure(values=titles)
        self.input_status.set(f"Found {len(titles)} visible window(s)")
    def apply_input_config(self) -> bool:
        self.settings.capture_source = "window" if self.source.get() == "Window" else "monitor"
        self.settings.monitor = int(self.monitor.get())
        self.settings.window_title = self.window_title.get().strip()
        self.settings.confidence = float(self.confidence.get())
        mapping = {label: var.get().strip().lower() for label, var in self.action_vars.items() if var.get().strip()}
        duplicates = [key for key in set(mapping.values()) if list(mapping.values()).count(key) > 1]
        if duplicates:
            messagebox.showerror("Input configuration", f"Each key can only be assigned once: {', '.join(duplicates)}")
            return False
        self.settings.action_keys = mapping
        self.settings.class_to_key = {label: key for label, key in mapping.items() if label in self.settings.class_names}
        if self.controller is not None:
            self.controller.release_all(); self.controller.mapping = self.settings.class_to_key
            self.controller.states = {label: [0, 0, False] for label in self.settings.class_to_key}
        try:
            self.settings.save(self.config_path)
        except OSError as exc:
            messagebox.showerror("Configuration", f"Could not save {self.config_path}: {exc}")
            return False
        self.input_status.set(f"Saved configuration with {len(mapping)} mapping(s)")
        return True

    def begin_key_capture(self, label: str) -> None:
        if self.capturing_label is not None: return
        self.capturing_label = label; self.key_buttons[label].configure(text="Press key…")
        self.input_status.set(f"Press a key for {label} (Esc cancels)")
        self.root.bind_all("<Key>", self._capture_key)

    def _capture_key(self, event: tk.Event) -> str:
        label = self.capturing_label
        if label is None: return "break"
        key = event.keysym.lower()
        if key in {"escape", "f12"}:
            self._finish_key_capture(label); return "break"
        if key == "return": key = "enter"
        elif key == "prior": key = "pageup"
        elif key == "next": key = "pagedown"
        elif key == "backspace": key = "backspace"
        self.action_vars[label].set(key)
        self._finish_key_capture(label)
        return "break"

    def _finish_key_capture(self, label: str) -> None:
        self.root.unbind_all("<Key>"); self.capturing_label = None; self.key_buttons[label].configure(text="Set key")
        self.input_status.set(f"Key set for {label}; apply mappings to save")

    def clear_key(self, label: str) -> None:
        self.action_vars[label].set(""); self.input_status.set(f"Mapping cleared for {label}")

    @staticmethod
    def _overlaps(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
        left = max(first[0], second[0]); top = max(first[1], second[1])
        right = min(first[2], second[2]); bottom = min(first[3], second[3])
        intersection = max(0.0, right - left) * max(0.0, bottom - top)
        first_area = max(1.0, first[2] - first[0]) * max(1.0, first[3] - first[1])
        return intersection / first_area >= 0.15

    def test_action(self, action: str) -> None:
        key = self.action_vars[action].get().strip().lower()
        if not key:
            messagebox.showwarning("Input configuration", f"Set a key for {action} first.")
            return
        try:
            KeyboardController.tap_key(key)
            self.input_status.set(f"Tested {action} ({key})")
        except ValueError as exc:
            messagebox.showerror("Input configuration", str(exc))

    def toggle_input(self) -> None:
        if self.keyboard_enabled:
            self.keyboard_enabled = False
            if self.controller is not None: self.controller.release_all()
            self.input_button.configure(text="Arm input"); self.input_status.set("Input disarmed")
            return
        if not self.apply_input_config(): return
        if not self.settings.action_keys:
            messagebox.showwarning("Input configuration", "Configure at least one class-to-key mapping first.")
            return
        self.keyboard_enabled = True
        self.input_button.configure(text="Disarm input"); self.input_status.set("Input armed")
        logger.info("input actions armed: %s", self.settings.action_keys)

    def emergency_stop(self) -> None:
        self.keyboard_enabled = False
        self.running = False
        if self.controller is not None: self.controller.release_all()
        self.input_button.configure(text="Arm input")
        self.input_status.set("Emergency stop: input disarmed")
        self.status.set("Emergency stop: keyboard disabled")

    @staticmethod
    def _f12_pressed() -> bool:
        try:
            import ctypes
            return bool(ctypes.windll.user32.GetAsyncKeyState(0x7B) & 1)
        except (AttributeError, OSError):
            return False
    def close(self) -> None: self.stop(); self.root.destroy()
    def run(self) -> None: self.root.mainloop()
