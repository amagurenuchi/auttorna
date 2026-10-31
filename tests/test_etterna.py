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


def test_nowplaying_display_strips_msd_before_matching_chart(tmp_path):
    root = tmp_path / "Etterna"
    song = root / "Songs" / "Pack" / "Song"
    song.mkdir(parents=True)
    (root / "nowplaying.txt").write_text(
        "Test Song by Test Artist in Pack MSD: 27.38 - @ 27.38x", encoding="utf-8"
    )
    chart = song / "chart.sm"
    chart.write_text(
        "#TITLE:Test Song;#ARTIST:Test Artist;#BPMS:0=120;#NOTES:\n"
        "dance-single:\n:\nChallenge:\n:\n0:\n1000;",
        encoding="utf-8",
    )

    selection = find_selection(root)

    assert selection and selection.title == "Test Song"
    assert selection.artist == "Test Artist"
    assert selection.group == "Pack"
    assert selection.chart_path == chart
    assert selection.rate == 27.38


def test_msd_is_not_used_as_rate_when_no_playback_rate_is_present(tmp_path):
    root = tmp_path / "Etterna"
    root.mkdir()
    (root / "nowplaying.txt").write_text(
        "Test Song by Test Artist in Pack MSD: 27.38", encoding="utf-8"
    )

    selection = find_selection(root)

    assert selection and selection.rate == 1.0
