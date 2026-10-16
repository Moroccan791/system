"""Typing sound system: shared ASS/audio timing, the key bank, row caps."""

import re
import wave

from clipper.asr.base import Word
from clipper.captions.block import (build_block_ass, hook_type_marks,
                                    hook_word_times)
from clipper.captions.keysfx import synthesize_bank

STYLE = {"captions": {"font_name": "Montserrat", "primary_text_color": "#FDFCFD",
                      "outline_color": "#275B77", "position": {"margin_v": 420},
                      "block": {"base_size_ass": 84, "emphasis_scale": 1.6}}}


def W(start, dur, text):
    return Word(text=text, start=start, end=start + dur)


def test_hook_marks_are_monotonic_and_end_with_enter():
    lines = ["SHE STOLE", "HIS CAR KEYS"]
    times = hook_word_times(lines)
    flat = [t for row in times for t in row]
    assert flat == sorted(flat) and len(flat) == 5
    marks = hook_type_marks(lines)
    assert [k for _, k in marks] == ["key"] * 5 + ["enter"]
    assert marks[-1][0] > flat[-1]


def test_typed_hook_events_replace_each_other_never_overlap():
    ass, _ = build_block_ass([W(0.0, 0.3, "Hello.")], STYLE, end=6.0,
                             hook_lines=["HE STOLE HER HEART"])
    hook = [ln for ln in ass.splitlines() if ",Hook," in ln]
    # four words -> four typed steps, each ending when the next begins
    assert len(hook) == 4
    spans = []
    for ln in hook:
        m = re.match(r"Dialogue: 3,([\d:.]+),([\d:.]+),Hook", ln)
        spans.append((m.group(1), m.group(2)))
    for (_, e1), (s2, _) in zip(spans, spans[1:]):
        assert e1 == s2
    assert "HE STOLE HER HEART" in hook[-1]


def test_untyped_hook_stays_whole_line():
    style = {"captions": dict(STYLE["captions"],
                              block={"typing_hook": False})}
    ass, _ = build_block_ass([W(0.0, 0.3, "Hello.")], style, end=6.0,
                             hook_lines=["HE STOLE HER HEART"])
    hook = [ln for ln in ass.splitlines() if ",Hook," in ln]
    assert len(hook) == 1 and "HE STOLE HER HEART" in hook[0]


def test_blocks_never_exceed_two_rows_by_default():
    sentence = ("alpha bravo charlie delta echo foxtrot golf hotel india "
                "juliet kilo lima mike november oscar papa").split()
    words = [W(i * 0.25, 0.2, t) for i, t in enumerate(sentence)]
    words[-1] = W(words[-1].start, 0.2, words[-1].text + ".")
    ass, blocks = build_block_ass(words, STYLE, end=8.0)
    assert blocks  # chunks of <= 4 words
    assert all(len(b["text"].split()) <= 4 for b in blocks)
    events = []
    for ln in ass.splitlines():
        if ",Block," not in ln:
            continue
        m = re.match(r"Dialogue: \d,([\d:.]+),([\d:.]+),Block", ln)
        p = re.search(r"\\pos\(([\d.]+),([\d.]+)\)\\fs([\d.]+)", ln)
        if m and p:
            # words are baseline-aligned: top + ~0.8*size is the baseline
            events.append((m.group(1), float(p.group(2)) + 0.8 * float(p.group(3))))
    for b in blocks:
        def _s(ts):
            h, mnt, s = ts.split(":")
            return int(h) * 3600 + int(mnt) * 60 + float(s)
        bases = sorted(y for start, y in events
                       if b["start"] - 0.01 <= _s(start) < b["end"])
        rows = 1 + sum(1 for a, z in zip(bases, bases[1:]) if z - a > 20) if bases else 0
        assert rows <= 2, f"block {b['text']!r} spans {rows} rows"


def test_render_mixes_keystrokes_and_writes_qc_report(tmp_path):
    """End to end: typed hook -> audible key clicks in the mix + .qc.json."""
    import subprocess

    import numpy as np

    from clipper.captions import run_captions
    from clipper.captions.block import hook_type_marks
    from clipper.ffmpeg import ffmpeg_exe

    src = tmp_path / "src.mp4"
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=540x960:d=3:r=30", "-f", "lavfi", "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                    "-t", "3", str(src)], check=True, capture_output=True)
    words = [W(0.30, 0.25, "She"), W(0.60, 0.25, "lied"),
             W(0.90, 0.25, "to"), W(1.20, 0.30, "him.")]
    out = tmp_path / "out.mp4"
    result = run_captions(src, out, words=words, mode="block",
                          hook="SHE LIED", work_name="test-typing")
    assert result.output and out.exists()
    assert (tmp_path / "out.qc.json").exists()  # QC ran on the render

    raw = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(out),
                          "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32)

    def rms(t0, t1):
        seg = audio[int(t0 * 48000): int(t1 * 48000)]
        return float(np.sqrt((seg ** 2).mean()))

    mark = hook_type_marks(["SHE LIED"])[0][0]  # first typed word
    click = rms(mark - 0.01, mark + 0.09)
    quiet = rms(2.30, 2.45)  # silence out here: no words, no marks
    assert click > 5 * quiet + 0.005


def test_key_bank_variants_are_short_distinct_48k(tmp_path):
    written = synthesize_bank(tmp_path)
    assert len(written) == 6
    blobs = []
    for p in written:
        with wave.open(str(p)) as wf:
            assert wf.getframerate() == 48000
            ms = wf.getnframes() / wf.getframerate() * 1000
            assert 30 <= ms <= 200
            blobs.append(p.read_bytes())
    assert len(set(blobs)) == 6  # no two variants identical
