import numpy as np

from screen_detector.capture import CaptureFrame, CaptureTarget, LatestFrameSlot, SharedMemoryFrameSlot


def test_latest_frame_slot_overwrites_stale_frame():
    target = CaptureTarget(0, 0, 1, 1, "test")
    slot = LatestFrameSlot()
    first = CaptureFrame(np.zeros((1, 1, 3), dtype=np.uint8), 1, target)
    second = CaptureFrame(np.ones((1, 1, 3), dtype=np.uint8), 2, target)
    slot.publish(first)
    slot.publish(second)
    assert slot.get_latest() is second
    assert slot.get_latest() is None


def test_shared_memory_frame_slot_round_trip():
    target = CaptureTarget(0, 0, 2, 2, "test")
    frame = CaptureFrame(np.full((2, 2, 3), 7, dtype=np.uint8), 123, target)
    slot = SharedMemoryFrameSlot(frame.frame.shape)
    try:
        slot.publish(frame)
        view = slot.read_latest()
        assert view is not None
        image, timestamp = view
        assert timestamp == 123
        assert np.array_equal(image, frame.frame)
    finally:
        slot.close()
        slot.unlink()
