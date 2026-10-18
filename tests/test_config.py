import json

from screen_detector.config import Settings


def test_config_loads_nested_values(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"weights": "x", "class_names": ["a"], "capture": {"source": "window", "window_title": "Game"}}))
    s = Settings.load(p)
    assert s.capture_source == "window" and s.window_title == "Game" and s.class_names == ["a"]
