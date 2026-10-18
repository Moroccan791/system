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
      [--treat on|off]   quality treatment B on the base (default on)
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


# Quality treatment "B" (adopted as the default 2026-10-16 after an A/B on
# the 57-men clip): light denoise -> mild sharpen -> fine temporal grain.
# On low-res sources (a face a few hundred px wide, upscaled 2-3x) this
# removes the blocky upscale mush and reads filmic instead of blurry.
# Costs minutes per clip at preset medium; --treat off skips it.
TREAT_VF = "hqdn3d=3:2:6:4,unsharp=5:5:0.45:3:3:0.15,noise=alls=7:allf=t"


def treat_base(base: Path, job: Path) -> Path:
    sys.path.insert(0, str(ROOT))
    from clipper.ffmpeg import ffmpeg_exe
    out = job / "base_treated.mp4"
    # crf18/veryfast for the INTERMEDIATE (was crf16/medium: a 60s
    # clip made a ~1GB treated file and every downstream stage -
    # transitions, matte, composite - paid for decoding it; the
    # treatment look lives in the filter chain, and the delivery
    # encode is capped at 10M anyway)
    r = run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(base),
             "-vf", TREAT_VF, "-c:v", "libx264", "-crf", "18",
             "-preset", "veryfast", "-c:a", "copy", str(out)])
    if r.returncode != 0:
        raise RuntimeError(f"base treatment failed: {r.stderr[-300:]}")
    return out


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
        kept = []
        for i in tl["items"]:
            if i["type"] in ("poster", "card", "counter", "list", "process",
                             "vector", "endcard") \
                    or (i["type"] == "fx" and i.get("kind") == "opening"):
                kept.append(i)
            elif i["type"] == "proof":
                # the receipt IS the argument: never vanish it in a
                # fallback - downgrade the proof card to a caption
                # poster (hot phrases become payoff words)
                rows = []
                for ph in i.get("phrases") or []:
                    t0 = float(ph.get("at") or i["at"])
                    kind = "pay" if ph.get("hot") else "word"
                    rows.append([{"w": w, "at": round(t0 + 0.22 * k, 2),
                                  "kind": kind}
                                 for k, w in enumerate(
                                     str(ph["text"]).split())])
                if rows:
                    kept.append({"type": "poster", "at": i["at"],
                                 "until": min(float(i["until"]),
                                              float(i["at"]) + 3.0),
                                 "rows": rows})
        tl["items"] = kept
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
    # dense speech: a chunk's +0.45 tail can run into the next chunk
    # (validator: same-type overlap >0.25s is a defect) and the last
    # tail can run past the duration - clamp, keeping every stack's
    # last-word dwell floor
    for prev, cur in zip(items, items[1:]):
        last = max(w["at"] for r in prev["rows"] for w in r)
        prev["until"] = round(max(last + 0.21,
                                  min(prev["until"], cur["at"] + 0.24)), 2)
    if items:
        last = max(w["at"] for r in items[-1]["rows"] for w in r)
        items[-1]["until"] = round(max(min(items[-1]["until"], duration),
                                       min(last + 0.21, duration)), 2)
    return {"version": 1, "fps": FPS, "width": 1080, "height": 1920,
            "duration": duration, "brand": {"accent": "#FFC531"},
            "items": items}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # absolute everywhere: subprocesses run with different cwds
    tl_path, base, tr_path, job = (Path(a).resolve() for a in args[:4])
    opt = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] \
        if k in sys.argv else d
    flag = lambda k: k in sys.argv  # noqa: E731 -- boolean switches
    seed = int(opt("--seed", 7))
    typing = opt("--typing-sound", "on")
    job.mkdir(parents=True, exist_ok=True)
    tl_src = json.loads(tl_path.read_text())
    transcript = json.loads(tr_path.read_text())
    if isinstance(transcript, dict):
        transcript = transcript.get("words") or []
    log: dict = {"seed": seed, "timeline": str(tl_path),
                 "base": str(base), "choices": {}, "levels": []}

    if opt("--treat", "on") != "off":
        base = treat_base(base, job)
        log["treatment"] = "B (hqdn3d+unsharp+grain, crf18); base_treated.mp4"
        log["base_treated"] = str(base)

    theme = load_theme(opt("--theme"), base, tl_src, log)
    if opt("--font"):
        # whole-video font pack choice (motion/fonts.py lists them);
        # overrides the theme's pack, never the brand accent
        if opt("--font") in ("montserrat", "anton", "bebas",
                             "grotesk", "serif", "archivo", "poppins",
                             "luckiest", "oblique", "serifbi", "sansitalic",
                             "regular", "displaybook", "grande"):
            theme["fontPack"] = opt("--font")
            log["font_pack"] = opt("--font")
        else:
            log["font_pack"] = f"unknown {opt('--font')!r} - ignored"
    # adaptive caption shade: measure what actually sits behind the
    # caption zone; bright footage earns a deeper ground plate
    try:
        import cv2
        cap = cv2.VideoCapture(str(base))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 90
        lum = []
        for frac in (0.15, 0.4, 0.65, 0.9):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * frac))
            ok, fr = cap.read()
            if ok:
                zone = fr[int(0.66 * fr.shape[0]):int(0.86 * fr.shape[0])]
                lum.append(float(zone.mean()) / 255.0)
        cap.release()
        if lum and sum(lum) / len(lum) > 0.52:
            theme["captionShade"] = 0.4
            log["caption_shade"] = (f"zone luminance "
                                    f"{sum(lum) / len(lum):.2f} -> shade 0.4")
    except Exception as e:  # measurement must never block a render
        log["caption_shade"] = f"skipped ({e})"
    # fit captions to THIS video, not to taste: track the face and
    # hand every un-zoned poster the measured caption zone (authored
    # zones and behind/place3d items are deliberate and stay put).
    # --no-auto-zones opts out; --face-report just forces the log.
    auto_zone = None
    if not flag("--no-auto-zones") or flag("--face-report"):
        fr = py("reframe.py", "--report", str(base))
        try:
            log["face_report"] = json.loads(fr.stdout)
            z = log["face_report"].get("recommended_caption_zone")
            if z and not flag("--no-auto-zones"):
                auto_zone = [max(0.30, min(z[0], 0.90)),
                             max(0.35, min(z[1], 0.95))]
                log["auto_zones"] = (f"poster zone {auto_zone} from "
                                     f"face bottom "
                                     f"{log['face_report'].get('face_bottom')}")
        except Exception:
            log["face_report"] = "unavailable"
    import numpy as np
    rng = np.random.default_rng(seed)
    kinds = ["flare", "flash", "leak", "bwflash"]
    rot = int(rng.integers(0, 4))
    sound_seed = seed * 100 + theme.get("soundSeedSalt", 0)
    log["choices"] = {"transition_rotation": rot,
                      "sound_seed": sound_seed,
                      "typing_sound": typing}

    for level in (0, 1, 2):
        if level == 2 and theme.get("name") == "whop":
            # A caption-only safety fallback is NOT a Whop deliverable.
            # If both full and simplified motion fail, return failure.
            log["levels"].append({"level": 2, "stage": "policy",
                                  "error": "Whop requires real motion graphics"})
            break
        tl = tl_src if level < 2 else plain_captions(
            transcript, tl_src.get("duration", 10))
        tl = json.loads(json.dumps(tl))
        tl["theme"] = {k: theme[k] for k in
                       ("radius", "glow", "speed", "easing", "fontMode",
                        "captionStyle", "captionShade", "fontPack",
                        "fonts", "colors")          # style card roles
                       if k in theme}
        tl.setdefault("brand", {})["accent"] = theme["accent"]
        if auto_zone:
            for it in tl["items"]:
                # proof cards get the face-safe zone too: the receipt
                # must never sit on the speaker's eyes (house rule).
                # phone inserts are deliberate full-bleed cutaways and
                # doodles are authored point annotations: both stay.
                if it["type"] in ("poster", "proof") and "zone" not in it \
                        and not it.get("behind") \
                        and not it.get("place3d"):
                    it["zone"] = list(auto_zone)
        if level == 1:
            tl = simplify(tl, 1)
        # branded end card: auto-injected when the timeline's brand
        # carries a name/handle and no endcard was authored
        brand = tl_src.get("brand") or {}
        if (brand.get("name") or brand.get("handle")) and \
                not any(i["type"] == "endcard" for i in tl["items"]):
            dur = float(tl_src.get("duration") or 10)
            tl["items"].append(
                {"type": "endcard", "at": round(dur - 1.3, 2),
                 "until": round(dur - 0.03, 2),
                 "title": brand.get("name") or brand.get("handle"),
                 **({"sub": brand["handle"]} if brand.get("handle")
                    and brand.get("name") else {})})
        auth_path = job / f"timeline_l{level}.json"
        auth_path.write_text(json.dumps(tl, indent=1))
        fx_path = job / f"timeline_fx_l{level}.json"
        tr_args = [str(base), str(auth_path), str(fx_path)]
        if theme.get("cutTransitions") == "hard":
            tr_args.append("--hard")
        r = py("transitions.py", *tr_args)
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
        behind_frames = None
        mask = None
        render_tl = fx_path
        grade = opt("--grade") or theme.get("grade")
        if grade:
            log.setdefault("choices", {})["grade"] = grade
        need_matte = any(it.get("behind") for it in fx["items"]) \
            or grade == "subject_pop"
        if need_matte:
            # subject_pop shares the behind-the-person matte: the
            # speaker keeps the grade, the room goes quiet behind them
            mask = job / "person_mask.mp4"
            if not mask.exists():
                m = py("matte.py", str(base), str(mask))
                if m.returncode != 0:
                    log["levels"].append(
                        {"level": level, "stage": "matte",
                         "error": (m.stderr or m.stdout)[-300:]})
                    continue
        if any(it.get("behind") for it in fx["items"]):
            # behind-the-person: matte once per job (pure function of
            # the base), then render the behind layer and the main
            # layer separately; composite stacks base -> behind ->
            # speaker -> main. A matte failure fails the level, never
            # silently drops the effect.
            mask = job / "person_mask.mp4"
            if not mask.exists():
                m = py("matte.py", str(base), str(mask))
                if m.returncode != 0:
                    log["levels"].append(
                        {"level": level, "stage": "matte",
                         "error": (m.stderr or m.stdout)[-300:]})
                    continue
            main_tl = json.loads(fx_path.read_text())
            behind_tl = json.loads(fx_path.read_text())
            behind_items = [i for i in main_tl["items"] if i.get("behind")]
            main_tl["items"] = [i for i in main_tl["items"]
                                if not i.get("behind")]
            behind_tl["items"] = behind_items
            render_tl = job / f"timeline_main_l{level}.json"
            render_tl.write_text(json.dumps(main_tl))
            behind_path = job / f"timeline_behind_l{level}.json"
            behind_path.write_text(json.dumps(behind_tl))
            behind_frames = job / f"behind_l{level}"
            rb = run(["node", str(HERE / "render.mjs"), str(behind_path),
                      str(behind_frames)], cwd=HERE)
            if rb.returncode != 0 or len(list(behind_frames.glob("*.png"))) < 10:
                log["levels"].append(
                    {"level": level, "stage": "render-behind",
                     "error": (rb.stderr or rb.stdout)[-300:]})
                continue
        r = run(["node", str(HERE / "render.mjs"), str(render_tl),
                 str(frames)], cwd=HERE)
        n_frames = len(list(frames.glob("*.png"))) if frames.exists() else 0
        if r.returncode != 0 or n_frames < 10:
            log["levels"].append({"level": level, "stage": "render",
                                  "error": (r.stderr or r.stdout)[-300:],
                                  "frames_rendered": n_frames})
            continue
        final = job / "final.mp4"
        cargs = [str(base), str(frames), str(fx_path), str(final)]
        if behind_frames is not None:
            cargs += ["--behind", str(behind_frames), "--mask", str(mask)]
        elif mask is not None:
            cargs += ["--mask", str(mask)]
        if grade:
            cargs += ["--grade", grade]
        c = py("composite.py", *cargs)
        if c.returncode != 0 or not final.exists():
            log["levels"].append({"level": level, "stage": "composite",
                                  "error": (c.stderr or c.stdout)[-300:]})
            continue
        # the QC needs the CLEAN base as well: the caption letters
        # themselves read as a face on the finished clip
        q = py("qc.py", str(fx_path), str(tr_path), str(final),
               str(frames), str(base))
        passed = q.returncode == 0
        log["levels"].append({"level": level, "qc_pass": passed,
                              "qc_tail": q.stdout.strip().split("\n")[0]
                              if q.stdout else ""})
        if not passed:
            continue
        snd = job / "final_s.mp4"
        sargs = [str(fx_path), str(final), str(snd),
                 "--typing-sound", typing, "--seed", str(sound_seed)]
        if opt("--music"):
            sargs += ["--music", str(Path(opt("--music")).resolve())]
            log["music_bed"] = opt("--music")
        s = py("sound.py", *sargs)
        log["sound_pass"] = s.returncode == 0 and snd.exists()
        log["sound_tail"] = s.stdout.strip()
        if not log["sound_pass"]:
            log["levels"].append({"level": level, "stage": "sound",
                                  "error": (s.stderr or s.stdout)[-500:]})
            continue
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
        # retention score (report-only) + posting pack: filed with
        # every shipped render so the next authoring round improves
        rt = py("retention.py", str(fx_path), str(tr_path))
        try:
            ret = json.loads(rt.stdout)
            log["retention"] = {"score": ret["score"],
                                "band": ret["band"],
                                "notes": ret["notes"]}
            (pack / "retention.json").write_text(
                json.dumps(ret, indent=1))
        except Exception:
            pass
        pk = py("postpack.py", str(fx_path), str(tr_path),
                str(pack / "packaging"), str(snd))
        if pk.returncode != 0:
            log["levels"].append({"level": level, "stage": "postpack",
                                  "error": (pk.stderr or pk.stdout)[-500:]})
            break  # a video without its required campaign pack is not done
        log["packaging"] = pk.stdout.strip()
        if flag("--fps60"):
            # optional 60 fps delivery master (motion-interpolated);
            # the QC'd 30 fps file stays the canonical render
            from clipper.ffmpeg import ffmpeg_exe
            out60 = job / "final_s60.mp4"
            r60 = run([ffmpeg_exe(), "-y", "-v", "error", "-i",
                       str(snd), "-vf",
                       "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:"
                       "me_mode=bidir", "-c:v", "libx264", "-crf", "17",
                       "-maxrate", "12M", "-bufsize", "24M", "-c:a",
                       "copy", str(out60)])
            log["fps60"] = str(out60) if r60.returncode == 0 \
                else "failed (30fps master unaffected)"
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
