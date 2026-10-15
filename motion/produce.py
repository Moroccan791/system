#!/usr/bin/env python3
"""Stage D orchestrator: one command from timeline+base to a packed,
QC-verified render (Parts 4+5).

Theme resolution (config only, no code change), seeded variation
(transition cycle + sound seed, logged), the fallback chain
(full -> simpler -> plain poster captions; a render is only called
done when QC passes), and a decision_log.json + Part-5 review pack
for every run.

Usage:
  python motion/produce.py <timeline.json> <base.mp4> <transcript.json>
      <job_dir> [--theme neon-dark] [--seed 7] [--typing-sound on]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FPS = 30


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if Path("/tmp/al2023/lib").exists():
        env["LD_LIBRARY_PATH"] = "/tmp/al2023/lib"
    return subprocess.run(cmd, capture_output=True, text=True,
                          env=env, **kw)


def py(script: str, *args: str) -> subprocess.CompletedProcess:
    return run([sys.executable, str(HERE / script), *args])


def load_theme(name: str | None, base: Path, tl: dict,
               log: dict) -> dict:
    theme = {}
    if name is None and (ROOT / "motion" / "brand.py").exists():
        out = py("brand.py", str(base)).stdout
        try:
            auto = json.loads(out)
            name = auto["theme"]
            log["auto_brand"] = auto
        except Exception:
            name = "high-energy"
    theme = json.loads((HERE / "themes" / f"{name}.json").read_text())
    if log.get("auto_brand", {}).get("accent_override"):
        theme["accent"] = log["auto_brand"]["accent_override"]
    if (tl.get("brand") or {}).get("accent"):  # campaign brand lock wins
        theme["accent"] = tl["brand"]["accent"]
    log["theme"] = theme["name"]
    return theme


def simplify(tl: dict, level: int) -> dict:
    tl = json.loads(json.dumps(tl))
    if level == 1:  # drop inserts/fx/chips, keep the argument
        tl["items"] = [i for i in tl["items"] if i["type"] in
                       ("poster", "card", "counter", "list", "process")
                       or (i["type"] == "fx" and i.get("kind") == "opening")]
    return tl


def plain_captions(transcript: list[dict], duration: float) -> dict:
    """Fallback level 2: word-chunked poster captions, nothing else."""
    items, chunk = [], []
    def flush():
        if not chunk:
            return
        rows, row = [], []
        for w in chunk:
            row.append({"w": w["text"], "at": round(w["start"], 2)})
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        items.append({"type": "poster",
                      "at": round(chunk[0]["start"], 2),
                      "until": round(chunk[-1]["end"] + 0.45, 2),
                      "zone": [0.66, 0.86], "rows": rows})
        chunk.clear()
    for w in transcript:
        chunk.append(w)
        if len(chunk) >= 6 or str(w["text"]).endswith((".", "?", "!")):
            flush()
    flush()
    return {"version": 1, "fps": FPS, "width": 1080, "height": 1920,
            "duration": duration, "items": items}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # absolute everywhere: subprocesses run with different cwds
    tl_path, base, tr_path, job = (Path(a).resolve() for a in args[:4])
    opt = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] \
        if k in sys.argv else d
    seed = int(opt("--seed", 7))
    typing = opt("--typing-sound", "on")
    job.mkdir(parents=True, exist_ok=True)
    tl_src = json.loads(tl_path.read_text())
    transcript = json.loads(tr_path.read_text())
    if isinstance(transcript, dict):
        transcript = transcript.get("words") or []
    log: dict = {"seed": seed, "timeline": str(tl_path),
                 "base": str(base), "choices": {}, "levels": []}

    theme = load_theme(opt("--theme"), base, tl_src, log)
    import numpy as np
    rng = np.random.default_rng(seed)
    kinds = ["flare", "flash", "leak", "bwflash"]
    rot = int(rng.integers(0, 4))
    sound_seed = seed * 100 + theme.get("soundSeedSalt", 0)
    log["choices"] = {"transition_rotation": rot,
                      "sound_seed": sound_seed,
                      "typing_sound": typing}

    for level in (0, 1, 2):
        tl = tl_src if level < 2 else plain_captions(
            transcript, tl_src.get("duration", 10))
        tl = json.loads(json.dumps(tl))
        tl["theme"] = {k: theme[k] for k in
                       ("radius", "glow", "speed", "easing", "fontMode")
                       if k in theme}
        tl.setdefault("brand", {})["accent"] = theme["accent"]
        if level == 1:
            tl = simplify(tl, 1)
        auth_path = job / f"timeline_l{level}.json"
        auth_path.write_text(json.dumps(tl, indent=1))
        fx_path = job / f"timeline_fx_l{level}.json"
        r = py("transitions.py", str(base), str(auth_path), str(fx_path))
        if r.returncode != 0:
            log["levels"].append({"level": level, "stage": "transitions",
                                  "error": r.stderr[-300:]})
            continue
        # seeded transition variety: rotate injected transition kinds
        fx = json.loads(fx_path.read_text())
        for it in fx["items"]:
            if it["type"] == "fx" and it.get("kind") in kinds:
                it["kind"] = kinds[(kinds.index(it["kind"]) + rot) % 4]
        fx_path.write_text(json.dumps(fx, indent=1))
        if py("validate.py", str(fx_path)).returncode != 0:
            log["levels"].append({"level": level, "stage": "validate"})
            continue
        frames = job / f"frames_l{level}"
        r = run(["node", str(HERE / "render.mjs"), str(fx_path),
                 str(frames)], cwd=HERE)
        n_frames = len(list(frames.glob("*.png"))) if frames.exists() else 0
        if r.returncode != 0 or n_frames < 10:
            log["levels"].append({"level": level, "stage": "render",
                                  "error": (r.stderr or r.stdout)[-300:],
                                  "frames_rendered": n_frames})
            continue
        final = job / "final.mp4"
        c = py("composite.py", str(base), str(frames), str(fx_path),
               str(final))
        if c.returncode != 0 or not final.exists():
            log["levels"].append({"level": level, "stage": "composite",
                                  "error": (c.stderr or c.stdout)[-300:]})
            continue
        q = py("qc.py", str(fx_path), str(tr_path), str(final),
               str(frames))
        passed = q.returncode == 0
        log["levels"].append({"level": level, "qc_pass": passed,
                              "qc_tail": q.stdout.strip().split("\n")[0]
                              if q.stdout else ""})
        if not passed:
            continue
        snd = job / "final_s.mp4"
        s = py("sound.py", str(fx_path), str(final), str(snd),
               "--typing-sound", typing, "--seed", str(sound_seed))
        log["sound_pass"] = s.returncode == 0
        log["sound_tail"] = s.stdout.strip()
        # Part-5 pack
        pack = job / "review_pack"
        pack.mkdir(exist_ok=True)
        run([sys.executable, str(HERE / "composite.py"), "--sheet",
             str(snd), str(fx_path), str(pack / "pack")])
        py("report.py", str(fx_path), str(tr_path), str(snd),
           str(pack / "qc_full"))
        (pack / "qc_v2.txt").write_text(q.stdout)
        if (job / "final_s.sound.json").exists():
            (pack / "sound_log.json").write_text(
                (job / "final_s.sound.json").read_text())
        log["verdict"] = f"PASS at level {level}"
        (job / "decision_log.json").write_text(json.dumps(log, indent=1))
        (pack / "decision_log.json").write_text(json.dumps(log, indent=1))
        print(json.dumps(log, indent=1))
        return 0
    log["verdict"] = "FAIL at all levels - not shipped"
    (job / "decision_log.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log, indent=1))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
