import threading
import time

from screen_detector.control import Scheduler, SendInputBackend


class FakeBackend:
    def __init__(self):
        self.events = []
        self.done = threading.Event()

    def press(self, lane, action=None):
        self.events.append(("press", lane, action))
        self.done.set()
        return 0

    def release(self, lane, action=None):
        self.events.append(("release", lane, action))
        return 0

    def release_all(self):
        self.events.append(("release_all",))


def test_scan_code_backend_is_disabled_without_os_input():
    backend = SendInputBackend({0: 30}, enabled=False)
    assert backend.press(0) == 0
    assert 0 in backend.held
    assert backend.release(0) == 0
    assert not backend.held


def test_scheduler_orders_and_issues_action():
    backend = FakeBackend()
    scheduler = Scheduler(backend, stale_timeout_ms=500)
    scheduler.start()
    try:
        scheduler.mark_frame()
        scheduler.arm()
        scheduler.schedule(time.perf_counter_ns() + 5_000_000, 2, "right", note_id=7)
        assert backend.done.wait(1.0)
        assert backend.events == [("press", 2, "right")]
        assert scheduler.stats.issued == 1
    finally:
        scheduler.stop()


def test_scheduler_disarm_clears_queue():
    backend = FakeBackend()
    scheduler = Scheduler(backend)
    scheduler.schedule(time.perf_counter_ns() + 1_000_000_000, 0)
    scheduler.disarm()
    assert scheduler.stats.cancelled == 1


def test_scan_code_backend_batches_simultaneous_actions():
    backend = SendInputBackend({0: 30, 1: 31}, enabled=False)
    assert backend.send_actions([(0, None, "press"), (1, None, "press")]) == 0
    assert backend.held == {0, 1}
    backend.send_actions([(0, None, "release"), (1, None, "release")])
    assert not backend.held
