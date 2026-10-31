"""Vision-gated runner: lock the chart clock before enabling input."""

from dataclasses import dataclass
import logging
import threading
import time

from bot.chart.schedule import Schedule
from bot.sync.matcher import ArrowObservation, ClockSample, align_observations, match_detection
from bot.vision.capture import RoiCapture
from bot.vision.detector import OnnxDetector
from bot.vision.tracker import Tracker

logger = logging.getLogger(__name__)
MIN_SYNC_MOTION_PX_S = 100.0


@dataclass(frozen=True)
class VisionConfig:
    model: str
    classes: tuple[str, ...]
    roi: tuple[int, int, int, int]
    backend: str = "dxcam"
    target_hz: int = 20
    input_size: int = 384
    confidence: float = 0.5
    receptor_y: float = 0.0
    scroll_speed_px_s: float | None = None
    # A single arrow is ambiguous: repeated lanes and chords can produce a
    # plausible but completely wrong chart offset. Require a short ordered
    # sequence before allowing the scheduler to send input.
    initial_notes: int = 8
    match_window_s: float = 0.12
    min_sync_span_s: float = 0.5
    runtime_correction_min_notes: int = 3
    runtime_correction_threshold_s: float = 0.08
    runtime_correction_window_s: float = 0.35
    provider: str = "auto"


class VisionGate:
    """Runs vision asynchronously and starts the scheduler only after lock."""

    def __init__(self, config: VisionConfig, schedule: Schedule, clock, scheduler) -> None:
        self.config, self.schedule = config, schedule
        self.clock, self.scheduler = clock, scheduler
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.locked = threading.Event()
        self.locked_song_t: float | None = None
        self.detected_song_t: float | None = None
        self.samples = 0
        self.last_error = ""

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="vision-gate", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        capture = None
        try:
            detector = OnnxDetector(self.config.model, list(self.config.classes), self.config.confidence, self.config.input_size, self.config.provider)
            capture = RoiCapture(self.config.roi, self.config.target_hz, self.config.backend)
            capture.start()
            tracker = Tracker()
            bootstrap_observations: list[ArrowObservation] = []
            last_arrival_by_col: dict[int, float] = {}
            correction_samples: list[ClockSample] = []
            used_correction_events: set[tuple[float, int, str]] = set()
            schedule_cutoff = float("-inf")
            frame_count = 0
            last_detection_log = 0.0
            logger.info("vision gate started: model=%s roi=%s target_hz=%d", self.config.model, self.config.roi, self.config.target_hz)
            while not self.stop_event.is_set():
                frame = capture.read()
                if frame is None:
                    time.sleep(0.001)
                    continue
                detections = detector.detect(frame.pixels, frame.captured_at)
                arrow_detections = [d for d in detections if d.cls.lower() == "arrow"]
                tracks = tracker.update(arrow_detections)
                # A static receptor can occasionally be classified as an
                # arrow. It must show real frame-to-frame motion before it is
                # allowed to influence speed estimation or clock matching.
                static_speed = self.config.scroll_speed_px_s
                moving_arrows = [
                    (detection, track) for detection, track in zip(arrow_detections, tracks)
                    # With a configured speed, do not gate detections using
                    # the tracker's measured velocity.
                    if static_speed is not None or abs(track.velocity) >= MIN_SYNC_MOTION_PX_S
                ]
                frame_count += 1
                now = time.perf_counter()
                if now - last_detection_log >= 2.0:
                    logger.info("vision status: frames=%d detections=%d arrows=%d receptors=%d estimated_speed=%.1f", frame_count, len(detections), sum(d.cls.lower() == "arrow" for d in detections), sum(d.cls.lower() == "receptor" for d in detections), tracker.scroll_speed)
                    last_detection_log = now
                receptor_y = self.config.receptor_y
                if receptor_y <= 0:
                    receptor_detections = [d.y for d in detections if d.cls.lower() == "receptor"]
                    if receptor_detections:
                        receptor_y = sum(receptor_detections) / len(receptor_detections)
                        logger.info("receptor_y bootstrapped from detector: %.1f", receptor_y)
                speed = static_speed if static_speed is not None else tracker.scroll_speed
                if speed <= 1:
                    continue
                for detection, track in moving_arrows:
                    if static_speed is not None:
                        # Static configuration is authoritative. The model's
                        # frame time and position are used, but no estimated
                        # speed or fitted tracker velocity enters this path.
                        arrival_t = detection.t_frame + (receptor_y - detection.y) / static_speed
                    else:
                        arrival_t = tracker.arrival_at(track, receptor_y)
                    if arrival_t is None:
                        continue
                    previous_arrival = last_arrival_by_col.get(detection.col)
                    if previous_arrival is not None and abs(arrival_t - previous_arrival) < 0.04:
                        continue
                    # The same tracked arrow is visible across many frames;
                    # treat it as one receptor crossing in both lock phases.
                    last_arrival_by_col[detection.col] = arrival_t
                    if not self.locked.is_set() and arrival_t is not None:
                        self.detected_song_t = self.clock.song_at(arrival_t)
                        bootstrap_observations.append(ArrowObservation(arrival_t, detection.col))
                        bootstrap_observations = bootstrap_observations[-32:]
                        alignment = align_observations(bootstrap_observations, list(self.schedule.events), minimum=self.config.initial_notes)
                        if alignment is not None and max(item.wall_t for item in alignment.observations) - min(item.wall_t for item in alignment.observations) >= self.config.min_sync_span_s:
                            self.clock.a = 1.0
                            self.clock.b = -alignment.offset
                            self.samples = len(alignment.events)
                            logger.info(
                                "vision sequence locked: offset=%.3fs notes=%d span=%.3fs residual=%.1fms first_chart_t=%.3fs",
                                alignment.offset,
                                len(alignment.events),
                                max(item.wall_t for item in alignment.observations) - min(item.wall_t for item in alignment.observations),
                                alignment.residual * 1000,
                                alignment.events[0].t,
                            )
                            now_song = self.clock.song_at(time.perf_counter())
                            self.locked_song_t = now_song
                            schedule_cutoff = now_song
                            upcoming = [event for event in self.schedule.events if event.t >= now_song]
                            self.scheduler.replace(upcoming)
                            self.locked.set()
                            self.scheduler.start()
                            break
                    elif self.locked.is_set() and arrival_t is not None:
                        # Keep watching after lock. A broad-but-local match
                        # window lets several consistent crossings recover a
                        # clock that drifted or started at the wrong offset;
                        # one bad detection can never move the schedule.
                        sample = match_detection(
                            detection, list(self.schedule.events), receptor_y, speed,
                            window_s=self.config.runtime_correction_window_s,
                            wall_to_song=self.clock.song_at, arrival_t=arrival_t,
                            used_events=used_correction_events,
                            min_song_t=self.clock.song_at(arrival_t) - 0.2,
                        )
                        if sample is None:
                            continue
                        event_key = (sample.event.t, sample.event.col, sample.event.kind)
                        used_correction_events.add(event_key)
                        correction_samples.append(sample)
                        correction_samples = correction_samples[-8:]
                        if len(correction_samples) < self.config.runtime_correction_min_notes:
                            continue
                        errors = [item.song_t - self.clock.song_at(item.wall_t) for item in correction_samples]
                        errors_sorted = sorted(errors)
                        correction = errors_sorted[len(errors_sorted) // 2]
                        spread = max(errors) - min(errors)
                        if abs(correction) < self.config.runtime_correction_threshold_s or spread > 0.05:
                            continue
                        old_song = self.clock.song_at(time.perf_counter())
                        self.clock.b += correction
                        now_song = self.clock.song_at(time.perf_counter())
                        schedule_cutoff = max(schedule_cutoff, old_song, now_song)
                        upcoming = [event for event in self.schedule.events if event.t >= schedule_cutoff]
                        self.scheduler.replace(upcoming)
                        self.samples += len(correction_samples)
                        logger.warning(
                            "vision corrected clock: shift=%+.3fs notes=%d spread=%.1fms",
                            correction, len(correction_samples), spread * 1000,
                        )
                        correction_samples.clear()
                        used_correction_events.clear()
                    # Before lock, no event is assigned using the provisional
                    # clock. Sequence alignment above is the only bootstrap
                    # path; this avoids the old self-reinforcing offset loop.
        except Exception as error:
            self.last_error = str(error)
            logger.exception("vision gate stopped before clock lock: %s", error)
        finally:
            if capture is not None:
                capture.close()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1.0)
