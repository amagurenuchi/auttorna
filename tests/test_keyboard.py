from screen_detector.keyboard import KeyboardController


def test_debounced_events_do_not_repeat(monkeypatch):
    sent = []
    controller = KeyboardController({"target": "a"}, activation_frames=2, release_frames=2, cooldown=0)
    monkeypatch.setattr(controller, "_send", lambda key, up: sent.append((key, up)))
    controller.update({"target"}, True); controller.update({"target"}, True); controller.update({"target"}, True)
    assert sent == [("a", False)]
    controller.update(set(), True); controller.update(set(), True)
    assert sent == [("a", False), ("a", True)]


def test_disabled_actions_never_press(monkeypatch):
    sent = []; controller = KeyboardController({"target": "a"}, 1, 1, 0)
    monkeypatch.setattr(controller, "_send", lambda key, up: sent.append((key, up)))
    controller.update({"target"}, False)
    assert sent == []
