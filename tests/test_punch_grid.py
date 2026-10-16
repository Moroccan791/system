"""Camera punches must visibly zoom the picture - a filter that silently
does nothing is worse than no feature. Real footage can't prove this (smooth
backgrounds and burned-in text match best at scale 1.00 even when zoomed),
so the proof source is a synthetic grid: sharp texture everywhere, measured
by template-matching a corner patch at 1.00x vs 1.09x."""
import subprocess

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from clipper import config
from clipper.captions.render import burn
from clipper.ffmpeg import ffmpeg_exe


def _grid_video(path, seconds=3):
    img = np.zeros((1920, 1080, 3), np.uint8)
    for x in range(0, 1081, 60):
        cv2.line(img, (x, 0), (x, 1920), (255, 255, 255), 2)
    for y in range(0, 1921, 60):
        cv2.line(img, (0, y), (1080, y), (200, 200, 200), 2)
    cv2.imwrite(str(path) + ".png", img)
    subprocess.run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                    "-loop", "1", "-t", str(seconds), "-i", str(path) + ".png",
                    "-r", "30", str(path)], check=True)


def _frame(video, t, out):
    subprocess.run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(t), "-i", str(video), "-frames:v", "1", str(out)],
                   check=True)
    return cv2.imread(str(out), cv2.IMREAD_GRAYSCALE)


def _best_scale(before, after):
    h, w = before.shape
    patch = before[int(h * 0.01):int(h * 0.10), int(w * 0.01):int(w * 0.20)]
    scores = {}
    for scale in (1.00, 1.09):
        tpl = cv2.resize(patch, None, fx=scale, fy=scale)
        scores[scale] = float(cv2.matchTemplate(after, tpl, cv2.TM_CCOEFF_NORMED).max())
    return scores


def test_camera_punch_actually_zooms(tmp_path):
    src = tmp_path / "grid.mp4"
    _grid_video(src)
    ass = tmp_path / "empty.ass"
    ass.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
        "-1,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:01:40.00,0:01:42.00,Default,,0,0,0,,far away\n")
    out = tmp_path / "punched.mp4"
    burn(src, out, ass, preset=config.PLATFORMS[config.DEFAULT_PLATFORM],
         fit="cover", target_size=(1080, 1920),
         punches=[{"at": 1.5, "strength": 1.0}])
    calm = _frame(out, 0.5, tmp_path / "calm.png")
    peak = _frame(out, 1.52, tmp_path / "peak.png")
    scores = _best_scale(calm, peak)
    assert scores[1.09] > scores[1.00], f"punch did not zoom: {scores}"
