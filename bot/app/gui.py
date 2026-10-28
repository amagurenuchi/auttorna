"""Tkinter control surface with visible runtime configuration."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
import yaml

from bot.app.controller import Controller, ControllerState
from bot.app.pickers import pick_receptor, pick_roi
from bot.etterna import EtternaWatcher, find_selection
from bot.app.vision_loop import VisionConfig


class BotGui:
    def __init__(self, controller: Controller | None = None, config_path: str = "config/default.yaml") -> None:
        self.controller = controller or Controller()
        self.config_path = Path(config_path)
        self.settings = self._load_settings()
        self.root = tk.Tk()
        self.root.title("StepMania / Etterna Hybrid Bot")
        self.root.geometry("760x620")
        chart_settings = self.settings.get("chart", {})
        vision = self.settings.get("vision", {})
        sync = self.settings.get("sync", {})
        input_settings = self.settings.get("input", {})
        self.chart = tk.StringVar(value=chart_settings.get("path", ""))
        self.rate = tk.StringVar(value=str(chart_settings.get("rate", 1.0)))
        self.auto_detect = tk.BooleanVar(value=chart_settings.get("auto_detect", True))
        self.etterna_root = tk.StringVar(value=chart_settings.get("etterna_root", ""))
        self.songs_root = tk.StringVar(value=chart_settings.get("songs_root", ""))
        self.step_type = tk.StringVar(value=chart_settings.get("step_type", "dance-single"))
        self.difficulty = tk.StringVar(value=chart_settings.get("difficulty", "Challenge"))
        self.model = tk.StringVar(value=vision.get("model", ""))
        self.weights = tk.StringVar(value=vision.get("weights", "weights.pt"))
        self.variant = tk.StringVar(value=vision.get("variant", "nano"))
        self.backend = tk.StringVar(value=vision.get("backend", "dxcam"))
        self.roi = tk.StringVar(value=", ".join(map(str, vision.get("roi", [0, 0, 0, 0]))))
        self.target_hz = tk.StringVar(value=str(vision.get("target_hz", 20)))
        self.input_size = tk.StringVar(value=str(vision.get("input_size", 384)))
        self.confidence = tk.StringVar(value=str(vision.get("confidence", 0.5)))
        self.receptor_y = tk.StringVar(value=str(sync.get("receptor_y", 0)))
        self.scroll_speed = tk.StringVar(value="" if sync.get("scroll_speed_px_s") is None else str(sync["scroll_speed_px_s"]))
        self.latency = tk.StringVar(value=str(input_settings.get("input_latency_s", 0.0)))
        self.start_delay = tk.StringVar(value=str(input_settings.get("start_delay_s", 0.0)))
        keys = self._load_keymap(input_settings.get("keymap", "config/keymap.yaml"))
        self.key_vars = [tk.StringVar(value=keys.get(index, "")) for index in range(4)]
        self.status = tk.StringVar(value=ControllerState.IDLE.value)
        self.selection_status = tk.StringVar(value="Etterna autodetect is idle")
        self.watcher: EtternaWatcher | None = None
        self._build()
        self.root.bind_all("<F12>", lambda _event: self.stop())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1000, self.poll_etterna)

    def _load_settings(self) -> dict:
        try:
            return yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return {}

    def _load_keymap(self, path: str) -> dict[int, str]:
        try:
            raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
            return {int(key): str(value) for key, value in raw.get("keys", {}).items()}
        except (OSError, yaml.YAMLError, ValueError):
            return {}

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        chart_tab, vision_tab, input_tab = (ttk.Frame(notebook, padding=10) for _ in range(3))
        notebook.add(chart_tab, text="Song & play")
        notebook.add(vision_tab, text="Vision")
        notebook.add(input_tab, text="Timing & keys")
        self._build_chart_tab(chart_tab)
        self._build_vision_tab(vision_tab)
        self._build_input_tab(input_tab)
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Button(bottom, text="Arm / Start", command=self.start).pack(side="left")
        ttk.Button(bottom, text="Stop / release (F12)", command=self.stop).pack(side="left", padx=6)
        ttk.Button(bottom, text="Save settings", command=self.save_settings).pack(side="right")
        ttk.Label(outer, textvariable=self.status).pack(anchor="w", pady=(8, 0))

    def _field(self, parent: ttk.Frame, row: int, label: str, variable: tk.Variable, width: int = 34) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=variable, width=width).grid(row=row, column=1, sticky="ew", pady=4)

    def _build_chart_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Checkbutton(parent, text="Autodetect selected Etterna song and rate", variable=self.auto_detect).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self._field(parent, 1, "Etterna folder", self.etterna_root)
        ttk.Button(parent, text="Browse", command=lambda: self.pick_dir(self.etterna_root)).grid(row=1, column=2)
        self._field(parent, 2, "Songs folder (optional)", self.songs_root)
        ttk.Button(parent, text="Browse", command=lambda: self.pick_dir(self.songs_root)).grid(row=2, column=2)
        ttk.Button(parent, text="Detect now", command=self.detect_now).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(parent, textvariable=self.selection_status, wraplength=620).grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 10))
        self._field(parent, 5, "Chart file", self.chart)
        ttk.Button(parent, text="Browse", command=self.browse_chart).grid(row=5, column=2)
        self._field(parent, 6, "Rate", self.rate, 10)
        self._field(parent, 7, "Steps type", self.step_type)
        self._field(parent, 8, "Difficulty", self.difficulty)

    def _build_vision_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self._field(parent, 0, "ONNX model", self.model)
        ttk.Button(parent, text="Browse", command=lambda: self.pick_file(self.model, [("ONNX model", "*.onnx")])).grid(row=0, column=2)
        self._field(parent, 1, "RF-DETR weights", self.weights)
        ttk.Button(parent, text="Browse", command=lambda: self.pick_file(self.weights, [("PyTorch weights", "*.pt *.pth")])).grid(row=1, column=2)
        ttk.Button(parent, text="Generate ONNX", command=self.generate_model).grid(row=2, column=1, sticky="w", pady=(2, 8))
        self._field(parent, 3, "RF-DETR variant", self.variant)
        self._field(parent, 4, "Capture backend", self.backend)
        self._field(parent, 5, "ROI: left, top, right, bottom", self.roi)
        ttk.Button(parent, text="Pick ROI from screen", command=self.pick_roi).grid(row=5, column=2, sticky="w")
        self._field(parent, 6, "Vision rate (Hz)", self.target_hz, 10)
        self._field(parent, 7, "Model input size", self.input_size, 10)
        self._field(parent, 8, "Detection confidence", self.confidence, 10)

    def _build_input_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self._field(parent, 0, "Receptor Y in ROI", self.receptor_y, 10)
        ttk.Button(parent, text="Pick receptor line", command=self.pick_receptor).grid(row=0, column=2, sticky="w")
        self._field(parent, 1, "Scroll speed px/s (blank = estimate)", self.scroll_speed, 10)
        self._field(parent, 2, "Input latency seconds", self.latency, 10)
        self._field(parent, 3, "Wait before song clock starts (s)", self.start_delay, 10)
        ttk.Label(parent, text="Lane keys").grid(row=4, column=0, sticky="w", pady=(16, 4))
        for index, variable in enumerate(self.key_vars):
            ttk.Label(parent, text=f"Lane {index + 1}").grid(row=5 + index, column=0, sticky="w")
            ttk.Entry(parent, textvariable=variable, width=10).grid(row=5 + index, column=1, sticky="w", pady=3)
        ttk.Label(parent, text="F12 always stops and releases held keys.").grid(row=10, column=0, columnspan=2, sticky="w", pady=(16, 0))

    def pick_dir(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory()
        if selected:
            variable.set(selected)

    def pick_file(self, variable: tk.StringVar, filetypes: list[tuple[str, str]]) -> None:
        selected = filedialog.askopenfilename(filetypes=filetypes + [("All files", "*")])
        if selected:
            variable.set(selected)

    def browse_chart(self) -> None:
        self.pick_file(self.chart, [("StepMania charts", "*.sm *.ssc")])

    def generate_model(self) -> None:
        """Export in a worker so the Tkinter window stays responsive."""
        self.save_settings()
        self.status.set("Generating ONNX model; see the terminal for progress...")

        def work() -> None:
            try:
                from bot.util.export_onnx import export_model
                output = export_model(self.weights.get(), self.model.get() or "model.onnx", self.variant.get(), resolution=int(self.input_size.get()))
                self.root.after(0, lambda: (self.model.set(str(output)), self.status.set(f"Generated {output}")))
            except Exception as error:
                self.root.after(0, lambda: messagebox.showerror("ONNX export failed", str(error)))
                self.root.after(0, lambda: self.status.set("ONNX export failed; see terminal"))


    def pick_roi(self) -> None:
        try:
            pick_roi(self.root, lambda value: self.roi.set(", ".join(map(str, value))))
        except (RuntimeError, OSError) as error:
            messagebox.showerror("ROI picker", str(error))

    def pick_receptor(self) -> None:
        try:
            values = [int(value.strip()) for value in self.roi.get().split(",")]
            if len(values) != 4:
                raise ValueError
            pick_receptor(self.root, tuple(values), lambda value: self.receptor_y.set(str(value)))
        except ValueError:
            messagebox.showerror("Receptor picker", "Set a valid ROI first, or use Pick ROI from screen.")
        except (RuntimeError, OSError) as error:
            messagebox.showerror("Receptor picker", str(error))

    def detect_now(self) -> None:
        if not self.etterna_root.get().strip():
            self.selection_status.set("Choose the Etterna folder first (it must contain nowplaying.txt).")
            return
        selection = find_selection(self.etterna_root.get(), chart_root=self.songs_root.get() or None)
        if not selection:
            self.selection_status.set("No root-level nowplaying.txt found; choose a chart manually or check the Etterna folder.")
            return
        self.chart.set(str(selection.chart_path) if selection.chart_path else "")
        self.rate.set(str(selection.rate))
        match = str(selection.chart_path) if selection.chart_path else "no matching chart"
        self.selection_status.set(f"Detected: {selection.title} - {selection.artist} @ {selection.rate:.2f}x ({match})")

    def poll_etterna(self) -> None:
        if self.auto_detect.get() and self.etterna_root.get().strip():
            if self.watcher is None or str(self.watcher.root) != self.etterna_root.get().strip():
                self.watcher = EtternaWatcher(self.etterna_root.get(), self.songs_root.get() or None)
            selection = self.watcher.poll()
            if selection and selection.chart_path:
                self.chart.set(str(selection.chart_path))
                self.rate.set(str(selection.rate))
                self.selection_status.set(f"Detected: {selection.title} - {selection.artist} @ {selection.rate:.2f}x")
        self.root.after(1000, self.poll_etterna)

    def save_settings(self) -> None:
        self.settings.setdefault("chart", {}).update({"path": self.chart.get(), "rate": float(self.rate.get()), "auto_detect": self.auto_detect.get(), "etterna_root": self.etterna_root.get(), "songs_root": self.songs_root.get(), "step_type": self.step_type.get(), "difficulty": self.difficulty.get()})
        self.settings.setdefault("vision", {}).update({"model": self.model.get(), "weights": self.weights.get(), "variant": self.variant.get(), "backend": self.backend.get(), "roi": [int(value.strip()) for value in self.roi.get().split(",")], "target_hz": int(self.target_hz.get()), "input_size": int(self.input_size.get()), "confidence": float(self.confidence.get())})
        self.settings.setdefault("sync", {}).update({"receptor_y": float(self.receptor_y.get()), "scroll_speed_px_s": float(self.scroll_speed.get()) if self.scroll_speed.get().strip() else None})
        self.settings.setdefault("input", {}).update({"input_latency_s": float(self.latency.get()), "start_delay_s": float(self.start_delay.get())})
        self.config_path.write_text(yaml.safe_dump(self.settings, sort_keys=False), encoding="utf-8")
        self.status.set(f"Saved {self.config_path}")

    def start(self) -> None:
        try:
            if self.auto_detect.get() and not self.chart.get().strip():
                self.detect_now()
            if not self.chart.get().strip():
                raise ValueError("select a chart or configure Etterna autodetection")
            self.save_settings()
            keymap = {index: variable.get().strip() for index, variable in enumerate(self.key_vars) if variable.get().strip()}
            roi = tuple(int(value.strip()) for value in self.roi.get().split(","))
            speed = float(self.scroll_speed.get()) if self.scroll_speed.get().strip() else None
            vision = VisionConfig(self.model.get().strip(), ("arrow", "receptor"), roi, self.backend.get().strip(), int(self.target_hz.get()), int(self.input_size.get()), float(self.confidence.get()), float(self.receptor_y.get()), speed)
            self.controller.arm(self.chart.get(), float(self.rate.get()), self.step_type.get(), self.difficulty.get(), keymap=keymap, latency_s=float(self.latency.get()), vision_config=vision)
            self.controller.start(float(self.start_delay.get()))
            self.status.set(self.controller.state.value)
        except (ValueError, OSError) as error:
            messagebox.showerror("Cannot start", str(error))

    def stop(self) -> None:
        self.controller.stop()
        self.status.set(self.controller.state.value)

    def close(self) -> None:
        self.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
