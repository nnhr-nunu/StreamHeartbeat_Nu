from stream_heartbeat.ui.heart_paint import ECG_COLOR, ECG_PEN_MIN


def test_ecg_is_thick_red_not_chroma_green() -> None:
    assert ECG_COLOR.red() >= 180
    assert ECG_COLOR.green() < 80
    assert ECG_COLOR.blue() < 80
    assert ECG_PEN_MIN >= 8
