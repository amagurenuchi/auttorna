"""Vision-gated runner: lock the chart clock before enabling input."""

from dataclasses import dataclass
import logging
import threading
import time

from bot.chart.schedule import Schedule
from bot.sync.estimator import SyncEstimator
from bot.sync.matcher import match_detection
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
    # One valid arrow sample is enough to start; later samples are not needed
    # before scheduling because the first sample now initializes the clock.
    initial_notes: int = 1
    match_window_s: float = 0.12


class VisionGate:
    """Runs vision asynchronously and starts the scheduler only after lock."""

    def __init__(self, config: VisionConfig, schedule: Schedule, clock, scheduler) -> None:
        self.config, self.schedule = config, schedule
        self.clock, self.scheduler = clock, scheduler
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.locked = threading.Event()
        self.samples = 0
        self.last_error = ""

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="vision-gate", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        capture = None
        try:
            detector = OnnxDetector(self.config.model, list(self.config.classes), self.config.confidence, self.config.input_size, self.config.backend)
            capture = RoiCapture(self.config.roi, self.config.target_hz, self.config.backend)
            capture.start()
            tracker = Tracker()
            estimator = SyncEstimator()
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
                moving_arrows = [
                    detection for detection, track in zip(arrow_detections, tracks)
                    if abs(track.velocity) >= MIN_SYNC_MOTION_PX_S
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
                speed = self.config.scroll_speed_px_s or tracker.scroll_speed
                if speed <= 1:
                    continue
                for detection in moving_arrows:
                    bootstrap_window = max(self.config.match_window_s, 0.5) if self.samples < self.config.initial_notes else self.config.match_window_s
                    sample = match_detection(detection, list(self.schedule.events), receptor_y, speed, window_s=bootstrap_window, wall_to_song=self.clock.song_at)
                    if sample and estimator.update(sample):
                        self.samples += 1
                        logger.debug("sync sample: wall=%.6f song=%.6f residual=%.3fms", sample.wall_t, sample.song_t, sample.residual * 1000)
                        # Keep correcting the shared clock after the initial
                        # lock; the scheduler reads this clock for each future
                        # event, so corrections affect notes still ahead.
                        self.clock.a = estimator.clock.a
                        self.clock.b = estimator.clock.b
                        if not self.locked.is_set() and self.samples >= self.config.initial_notes:
                            now_song = self.clock.song_at(time.perf_counter())
                            upcoming = [event for event in self.schedule.events if event.t >= now_song]
                            self.scheduler.replace(upcoming)
                            logger.info("vision clock locked after %d samples at song_t=%.3f; %d upcoming events armed", self.samples, now_song, len(upcoming))
                            self.locked.set()
                            self.scheduler.start()
                            break
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
