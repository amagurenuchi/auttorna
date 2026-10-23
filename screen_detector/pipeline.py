from __future__ import annotations

from dataclasses import dataclass, field

from .model import Detection
from .timing import TimingRecorder
from .tracking import HitTimePredictor, NoteTracker, PredictedTap


@dataclass
class DryRunBackend:
    """Input backend used to validate scheduling without touching the keyboard."""

    events: list[tuple[int, int | str | None, str]] = field(default_factory=list)

    def press(self, lane: int, action: int | str | None = None) -> int:
        self.events.append((lane, action, "press"))
        return 0

    def release(self, lane: int, action: int | str | None = None) -> int:
        self.events.append((lane, action, "release"))
        return 0

    def release_all(self) -> None:
        return None

    def send_actions(self, actions: list[tuple[int, int | str | None, str]]) -> int:
        self.events.extend(actions)
        return 0


class VisionPipeline:
    """Tap-only tracking/prediction stage.

    This class deliberately accepts detector output rather than owning a model
    or capture device. That keeps the timestamp supplied by CaptureFrame intact
    and makes dry-run and replay tests deterministic.
    """

    def __init__(
        self,
        lanes: list[tuple[int, int]],
        receptor_y: float | None,
        scroll_speed_px_s: float | None,
        global_offset_ms: float = 0.0,
        pipeline_latency_ns: int = 0,
        timing: TimingRecorder | None = None,
    ) -> None:
        self.tracker = NoteTracker(lanes)
        self.predictor = HitTimePredictor(
            global_offset_ms=global_offset_ms,
            pipeline_latency_ns=pipeline_latency_ns,
        )
        self.receptor_y = receptor_y
        self.scroll_speed_px_s = scroll_speed_px_s
        self.timing = timing or TimingRecorder()

    def update(self, detections: list[Detection], captured_at_ns: int) -> list[PredictedTap]:
        with self.timing.stage("tracking"):
            result = self.tracker.update(detections, captured_at_ns)
        with self.timing.stage("prediction"):
            return self.predictor.predict(
                result,
                captured_at_ns,
                receptor_y=self.receptor_y,
                scroll_speed_px_s=self.scroll_speed_px_s,
            )
