from bot.chart.parser import parse_chart


def test_sm_timing_holds_mines_and_stops(tmp_path):
    chart = """#BPMS:0=120,4=240;#OFFSET:0;#STOPS:2=1;#NOTES:
dance-single:
:
Challenge:
:
0:
0000
1000
2000
3000
,
0000
2000
3000
M000
;"""
    path = tmp_path / "sample.sm"
    path.write_text(chart, encoding="utf-8")
    events = parse_chart(path, step_type="dance-single", difficulty="Challenge").events
    assert [(round(e.t, 3), e.col, e.kind) for e in events] == [
        (0.5, 0, "tap"), (2.0, 0, "hold_start"), (2.5, 0, "hold_end"),
        (3.25, 0, "hold_start"), (3.5, 0, "hold_end"), (3.75, 0, "mine")
    ]


def test_rate_scales_song_time(tmp_path):
    chart = "#BPMS:0=120;#NOTES:dance-single:\n:\nChallenge:\n:\n0:\n1000;"
    path = tmp_path / "sample.sm"
    path.write_text(chart, encoding="utf-8")
    schedule = parse_chart(path, step_type="dance-single", difficulty="Challenge")
    assert schedule.scaled(2).events[0].t == schedule.events[0].t / 2
