"""Lifecycle controller shared by the CLI, GUI, and future vision loop."""

from enum import StrEnum
import logging
import time

from bot.chart.parser import parse_chart
from bot.input.scheduler import Scheduler
from bot.input.keys import DEFAULT_KEYS
from bot.input.sendinput import SendInput
from bot.sync.clock import ClockModel
from bot.app.vision_loop import VisionConfig, VisionGate


class ControllerState(StrEnum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    LOCKING = "LOCKING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


class Controller:
    def __init__(self) -> None:
        self.state = ControllerState.IDLE
        self.clock = ClockModel()
        self.input = SendInput(DEFAULT_KEYS)
        self.scheduler = Scheduler(self.clock.song_to_wall, emit=self.input)
        self.chart = None
        self.vision_gate: VisionGate | None = None

    def arm(self, chart_path: str | None, rate: float = 1.0,
            step_type: str | None = None, difficulty: str | None = None,
            keymap: dict[int, str] | None = None, latency_s: float = 0.0,
            vision_config: VisionConfig | None = None) -> None:
        if chart_path:
            self.chart = parse_chart(chart_path, step_type=step_type, difficulty=difficulty)
            if rate != 1.0:
                self.chart = self.chart.scaled(rate)
            self.scheduler.replace(self.chart.events)
        if keymap is not None:
            self.input.release_all()
            self.input = SendInput(keymap)
            self.scheduler.emit = self.input
        self.scheduler.latency_s = latency_s
        self.vision_config = vision_config
        self.state = ControllerState.ARMED

    def start(self, delay_s: float = 0.0) -> None:
        if self.state not in {ControllerState.ARMED, ControllerState.LOCKING}:
            raise RuntimeError("controller must be armed before starting")
        # Anchor song zero to the instant the run starts. Vision sync may refine
        # this affine model later without changing the scheduler interface.
        if getattr(self, "vision_config", None) is not None:
            # Give bootstrap matching a provisional song zero. Vision samples
            # replace this offset once visible notes are matched.
            self.clock.b = -(time.perf_counter() + max(0.0, delay_s))
            self.state = ControllerState.LOCKING
            self.vision_gate = VisionGate(self.vision_config, self.chart, self.clock, self.scheduler)
            self.vision_gate.start()
            logging.getLogger(__name__).info("waiting for vision clock lock; no keystrokes will be sent yet")
            return
        self.clock.b = -(time.perf_counter() + max(0.0, delay_s))
        logging.getLogger(__name__).info("song clock anchored: starts in %.3fs; first scheduled event=%s", max(0.0, delay_s), self.chart.events[0].t if self.chart and self.chart.events else "none")
        self.state = ControllerState.RUNNING
        self.scheduler.start()

    def stop(self) -> None:
        if self.vision_gate is not None:
            self.vision_gate.stop()
            self.vision_gate = None
        self.scheduler.stop()
        self.input.release_all()
        self.state = ControllerState.STOPPED
