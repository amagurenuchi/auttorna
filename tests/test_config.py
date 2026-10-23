import json

from screen_detector.config import Settings


def test_config_loads_nested_values(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"weights": "x", "class_names": ["a"], "capture": {"source": "window", "window_title": "Game"}}))
    s = Settings.load(p)
    assert s.capture_source == "window" and s.window_title == "Game" and s.class_names == ["a"]


def test_config_loads_pipeline_fields(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "weights": "x", "class_names": ["a"],
        "roi": [1, 2, 300, 400], "lanes": [[10, 20]],
        "receptor_y": 350, "scroll_speed_px_per_s": 500,
        "display_refresh_hz": 144, "global_offset_ms": -3,
        "inference_backend": "directml", "input_backend": "sendinput",
    }))
    s = Settings.load(p)
    assert s.roi == (1, 2, 300, 400)
    assert s.lanes == [(10, 20)]
    assert s.receptor_y == 350
    assert s.inference_backend == "directml"
