from stream_heartbeat import __version__, display_version


def test_version_format() -> None:
    assert __version__ == "0.1.0"
    assert display_version() == "v0.1.0"
