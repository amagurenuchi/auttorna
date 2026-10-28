from bot.etterna import find_selection


def test_etterna_root_nowplaying_selection_and_chart_match(tmp_path):
    root = tmp_path / "Etterna"
    song = root / "Songs" / "Pack" / "Song"
    root.mkdir(parents=True)
    song.mkdir(parents=True)
    (root / "nowplaying_title").write_text("Test Song", encoding="utf-8")
    (root / "nowplaying_artist").write_text("Test Artist", encoding="utf-8")
    (root / "nowplaying_group").write_text("Pack", encoding="utf-8")
    (root / "nowplaying_rate").write_text("1.25", encoding="utf-8")
    (root / "nowplaying.txt").write_text("Test Song", encoding="utf-8")
    chart = song / "chart.sm"
    chart.write_text("#TITLE:Test Song;#ARTIST:Test Artist;#BPMS:0=120;#NOTES:\ndance-single:\n:\nChallenge:\n:\n0:\n1000;", encoding="utf-8")
    selection = find_selection(root)
    assert selection and selection.chart_path == chart
    assert selection.rate == 1.25
