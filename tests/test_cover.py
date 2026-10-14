"""Cover frames: the payoff still + hook typography must actually land on
the pixels - white first line, accent last line, scrims over the frame."""
import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image

from clipper.captions.cover import make_cover


def _frame(path, size=(540, 960)):
    Image.new("RGB", size, (140, 120, 110)).save(path)
    return path


def test_cover_draws_hook_lines(tmp_path):
    out = make_cover(_frame(tmp_path / "f.png"), tmp_path / "c.jpg",
                     ["THE STUDENTS", "GRADED THE TEACHER"], accent="#9BE82E")
    img = Image.open(out).convert("RGB")
    assert img.size == (540, 960)
    top = img.crop((40, 80, 500, 300))
    px = list(top.getdata())
    whites = sum(1 for r, g, b in px if r > 230 and g > 230 and b > 230)
    lime = sum(1 for r, g, b in px if g > 170 and r > 90 and b < 130)
    assert whites > 400, "first line text missing"
    assert lime > 400, "accent line text missing"


def test_cover_single_line_stays_white(tmp_path):
    out = make_cover(_frame(tmp_path / "f.png"), tmp_path / "c.jpg", ["ONE LINE"])
    px = list(Image.open(out).convert("RGB").crop((40, 80, 500, 240)).getdata())
    assert sum(1 for r, g, b in px if r > 230 and g > 230 and b > 230) > 300
