"""A campaign watermark must actually be on the pixels: topmost layer,
pinned the whole clip, where the brief asked for it. Proven on a synthetic
frame: a magenta stamp over a blue field - if the overlay chain silently
no-ops, the corner stays blue and this fails."""
import subprocess

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from clipper.captions.render import burn
from clipper.ffmpeg import ffmpeg_exe

ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 180
PlayResY: 320

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,HELLO
"""


def _mk_video(path, seconds=1.2):
    img = np.zeros((320, 180, 3), np.uint8)
    img[:] = (120, 40, 10)  # blue-ish field (BGR)
    cv2.imwrite(str(path) + ".png", img)
    subprocess.run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                    "-loop", "1", "-t", str(seconds), "-i", str(path) + ".png",
                    "-r", "30", "-pix_fmt", "yuv420p", str(path)], check=True)


def _frame(video, t, out):
    subprocess.run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(t), "-i", str(video), "-frames:v", "1", str(out)],
                   check=True)
    return cv2.imread(str(out))


def test_watermark_pinned_top_right(tmp_path):
    src = tmp_path / "src.mp4"
    _mk_video(src)
    wm = tmp_path / "wm.png"
    stamp = np.zeros((40, 100, 4), np.uint8)
    stamp[:] = (255, 0, 255, 255)  # opaque magenta
    cv2.imwrite(str(wm), stamp)
    ass = tmp_path / "c.ass"
    ass.write_text(ASS)
    out = tmp_path / "out.mp4"
    burn(src, out, ass, target_size=(180, 320),
         watermark={"file": str(wm), "position": "tr", "width_frac": 0.4})
    for t in (0.2, 1.0):  # first AND last seconds: pinned, not a flash
        f = _frame(out, t, tmp_path / f"f{t}.png")
        # stamp: 0.40*180=72px wide, at margin 36 -> x in [72,144), y in [36,65)
        corner = f[40:62, 78:140]
        assert (np.abs(corner.astype(int) - [255, 0, 255]).sum(axis=2) < 120).all(), \
            f"watermark missing at t={t}"
        plain = f[300, 10]                  # bottom-left: untouched field
        assert abs(int(plain[0]) - 120) < 40 and int(plain[2]) < 80
