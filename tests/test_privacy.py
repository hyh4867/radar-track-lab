from radar_track_lab.adsb import is_excluded


def test_dbflags_exclusion():
    assert is_excluded(1)  # military
    assert is_excluded(4)  # PIA
    assert is_excluded(8)  # LADD
    assert is_excluded(1 | 2)
    assert not is_excluded(0)
    assert not is_excluded(2)  # "interesting" only is kept
    assert not is_excluded(None)
