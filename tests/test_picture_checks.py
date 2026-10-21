"""A caption is judged on footage, not on a transition."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_a_caption_is_not_judged_on_a_smeared_frame() -> None:
    """A whip is a designed smear, and a face detector on a smear invents faces.

    Post 2 failed caption_face at a whip frame whose caption sat on a shirt, so
    the sample time steps off the transition - inside the same card, on real
    footage - and only when the manifest says where the cuts are.
    """
    import sys
    sys.path.insert(0, str(ROOT / "scripts" / "whop"))
    import qc_gate

    mid = 31.4
    t = qc_gate._sample_time(mid - 0.4, mid + 0.4, [mid])
    assert t != mid and abs(t - mid) > qc_gate.WHIP
    assert mid - 0.4 <= t <= mid + 0.4, "the sample must stay inside the card"
    assert qc_gate._sample_time(10.0, 11.0, []) == 10.5, "no cuts, no change"


def test_the_render_records_its_cuts_for_the_gate() -> None:
    src = (ROOT / "scripts" / "whop" / "render_clip.py").read_text()
    assert '"cuts"' in src, "the manifest has to carry where the whips are"
