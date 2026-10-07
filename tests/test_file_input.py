"""音声・動画ファイルをマイクの代わりに流す（β）。"""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path

import pytest

from stream_heartbeat.file_input import RATE, FilePlayer, load_pcm16


def _write_wav(path: Path, seconds: float, rate: int, channels: int) -> None:
    frames = array.array("h")
    for i in range(int(seconds * rate)):
        value = int(8000 * math.sin(2 * math.pi * 50 * i / rate))
        frames.extend([value] * channels)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames.tobytes())


def test_mono_16k_wav_is_read_as_is(tmp_path: Path) -> None:
    path = tmp_path / "heart.wav"
    _write_wav(path, 2.0, RATE, 1)
    pcm, cut = load_pcm16(path)
    assert len(pcm) == 2 * RATE and not cut


def test_other_wav_is_made_mono_16k_and_long_files_are_cut(qapp, tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    _write_wav(path, 3.0, 44100, 2)
    pcm, cut = load_pcm16(path, max_seconds=2.0)
    assert cut and len(pcm) == 2 * RATE
    pcm, cut = load_pcm16(path)
    # 変換で端の数ミリ秒が落ちることがある
    assert not cut and abs(len(pcm) - 3 * RATE) <= RATE // 100
    assert max(pcm) > 6000


def test_unreadable_file_raises(qapp, tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not audio")
    with pytest.raises(ValueError):
        load_pcm16(path)


def test_player_hands_out_sound_in_time_and_loops() -> None:
    player = FilePlayer(array.array("h", range(100)), rate=100)
    assert player.pull(0.0) == []
    player.play(10.0)
    assert len(player.pull(10.75)) == 75
    assert player.position == 0.75
    # 端を越えると頭から（くり返し再生）
    chunk = player.pull(11.25)
    assert len(chunk) == 50 and chunk[24] == 99 / 32768 and chunk[25] == 0.0
    assert player.playing and player.position == 0.25


def test_player_stops_at_the_end_without_loop() -> None:
    player = FilePlayer(array.array("h", [1000] * 100), rate=100)
    player.loop = False
    player.play(0.0)
    assert len(player.pull(2.0)) == 100
    assert not player.playing
    # もう一度押すと頭から
    player.play(5.0)
    assert player.playing and player.position == 0.0
