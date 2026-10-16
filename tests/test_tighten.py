"""Tightening math: which pauses die, and where every timestamp lands."""
import subprocess

import pytest

from clipper.captions.tighten import (assemble, dead_air_cuts, kept_duration,
                                      kept_segments, map_time)
from clipper.ffmpeg import ffmpeg_exe, probe


class W:
    def __init__(self, start, end):
        self.start, self.end = start, end


def test_only_real_pauses_are_cut():
    words = [W(0.0, 0.4), W(0.55, 0.9), W(2.2, 2.6), W(2.75, 3.0)]
    cuts = dead_air_cuts(words, min_gap=0.6)
    # 0.9 -> 2.2 is a 1.3s pause; 0.4->0.55 and 2.6->2.75 are breaths, kept
    assert cuts == [(1.04, 2.12)]


def test_pause_shrinks_to_a_breath_not_a_hole():
    words = [W(0.0, 1.0), W(2.3, 3.0)]
    (cs, ce), = dead_air_cuts(words, min_gap=0.6)
    kept_pause = (2.3 - 0.08) - 1.0 + (1.0 + 0.14) - 1.0 + (2.3 - (2.3 - 0.08)) - 0.08
    # simpler truth: the surviving pause is tail + head around the cut
    assert ce - cs == pytest.approx(1.3 - 0.14 - 0.08, abs=1e-6)


def test_kept_segments_and_duration():
    segs = kept_segments([(2.0, 3.0), (5.0, 5.5)], 8.0)
    assert segs == [(0.0, 2.0), (3.0, 5.0), (5.5, 8.0)]
    assert kept_duration(segs) == 6.5


def test_map_time_carries_timestamps_through_cuts():
    cuts = [(2.0, 3.0), (5.0, 5.5)]           # 1.5s removed in total
    assert map_time(1.0, cuts) == 1.0          # before: untouched
    assert map_time(2.5, cuts) == 2.0          # inside: lands on the cut start
    assert map_time(4.0, cuts) == 3.0          # after one cut: shifted by 1.0
    assert map_time(8.0, cuts) == 6.5          # after both: shifted by 1.5


def test_assemble_concatenates_kept_segments(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-t", "3", "-c:v", "libx264", "-c:a", "aac", str(src)],
                   check=True)
    out = assemble(src, [(0.0, 1.0), (2.0, 3.0)], tmp_path / "out.mp4")
    assert abs(probe(out).duration - 2.0) < 0.15
