"""FFmpeg / ffprobe wrapper: one place that knows how to spawn processes and
how to read/write video and audio as numpy arrays.

Binary resolution order:
    1. $CLIPPER_FFMPEG
    2. ffmpeg on PATH (what you have on Windows)
    3. the static build shipped by the `imageio-ffmpeg` wheel (sandbox / CI)

ffprobe is optional: when it is missing we parse `ffmpeg -i` output instead.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np

from .util import log

_CREATE_NO_WINDOW = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


class FFmpegError(RuntimeError):
    def __init__(self, args: Sequence[str], stderr: str) -> None:
        self.args_used = list(args)
        self.stderr = stderr
        tail = "\n".join(stderr.strip().splitlines()[-12:])
        super().__init__(f"ffmpeg failed: {' '.join(map(str, args[:8]))} ...\n{tail}")


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    import os

    env = os.environ.get("CLIPPER_FFMPEG")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # static fallback: pip install imageio-ffmpeg
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise FFmpegError(["ffmpeg"], f"no ffmpeg binary found ({exc})") from exc


@lru_cache(maxsize=1)
def ffprobe_exe() -> str | None:
    import os

    env = os.environ.get("CLIPPER_FFPROBE")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffprobe")
    if found:
        return found
    # imageio-ffmpeg ships only ffmpeg; look next to it just in case
    try:
        cand = Path(ffmpeg_exe()).with_name("ffprobe" + (".exe" if Path(ffmpeg_exe()).suffix == ".exe" else ""))
        return str(cand) if cand.exists() else None
    except Exception:
        return None


def run(args: Sequence[str | Path], *, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    cmd = [str(a) for a in args]
    proc = subprocess.run(
        cmd, capture_output=True, text=text, creationflags=_CREATE_NO_WINDOW
    )
    if check and proc.returncode != 0:
        raise FFmpegError(cmd, proc.stderr or "")
    return proc


@lru_cache(maxsize=64)
def has_filter(name: str) -> bool:
    out = run([ffmpeg_exe(), "-hide_banner", "-filters"]).stdout
    return bool(re.search(rf"\s{re.escape(name)}\s", out))


@lru_cache(maxsize=64)
def has_encoder(name: str) -> bool:
    out = run([ffmpeg_exe(), "-hide_banner", "-encoders"]).stdout
    return name in out


# ---------------------------------------------------------------------------
# probing
# ---------------------------------------------------------------------------
@dataclass
class MediaInfo:
    path: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    rotate: int = 0
    has_video: bool = False
    has_audio: bool = False
    audio_rate: int = 0
    audio_channels: int = 0
    vcodec: str | None = None
    acodec: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def is_portrait(self) -> bool:
        return self.height > self.width

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "raw"}
        return d


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")
_RES_RE = re.compile(r"(?<![\d.])(\d{2,5})x(\d{2,5})(?![\d.])")
_FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
_ARATE_RE = re.compile(r"(\d+)\s*Hz")
_ROT_RE = re.compile(r"rotate\s*:\s*(\d+)")


def parse_ffmpeg_input(stderr: str) -> MediaInfo:
    """Fallback probe: read `ffmpeg -i file` stderr."""
    info = MediaInfo(path="")
    m = _DUR_RE.search(stderr)
    if m:
        info.duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    vid_line = next((l for l in stderr.splitlines() if "Video:" in l), "")
    aud_line = next((l for l in stderr.splitlines() if "Audio:" in l), "")
    if vid_line:
        info.has_video = True
        mm = _RES_RE.search(vid_line)
        if mm:
            info.width, info.height = int(mm.group(1)), int(mm.group(2))
        fm = _FPS_RE.search(vid_line)
        if fm:
            info.fps = float(fm.group(1))
        info.vcodec = vid_line.split("Video:")[1].split()[0].strip(",")
        rm = _ROT_RE.search(stderr)
        if rm:
            info.rotate = int(rm.group(1))
    if aud_line:
        info.has_audio = True
        info.acodec = aud_line.split("Audio:")[1].split()[0].strip(",")
        am = _ARATE_RE.search(aud_line)
        if am:
            info.audio_rate = int(am.group(1))
        if "mono" in aud_line:
            info.audio_channels = 1
        elif "stereo" in aud_line:
            info.audio_channels = 2
    return info


def probe(path: str | Path) -> MediaInfo:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    probe_bin = ffprobe_exe()
    if probe_bin:
        proc = run([
            probe_bin, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ], check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                data = {}
            if data:
                return _info_from_ffprobe(path, data)
    # fallback
    stderr = run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], check=False).stderr or ""
    info = parse_ffmpeg_input(stderr)
    info.path = str(path)
    if info.width and info.height and info.rotate in (90, 270):
        info.width, info.height = info.height, info.width
    return info


def _info_from_ffprobe(path: Path, data: dict) -> MediaInfo:
    info = MediaInfo(path=str(path))
    fmt = data.get("format") or {}
    info.raw = data
    try:
        info.duration = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        info.duration = 0.0
    for st in data.get("streams", []):
        if st.get("codec_type") == "video" and not info.has_video:
            info.has_video = True
            info.width = int(st.get("width") or 0)
            info.height = int(st.get("height") or 0)
            info.vcodec = st.get("codec_name")
            rot = st.get("tags", {}).get("rotate")
            for sd in st.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = sd["rotation"]
            try:
                info.rotate = int(float(rot)) % 360 if rot is not None else 0
            except (TypeError, ValueError):
                info.rotate = 0
            rate = st.get("avg_frame_rate") or st.get("r_frame_rate") or "0/0"
            try:
                num, den = (rate.split("/") + ["1"])[:2]
                info.fps = float(num) / float(den) if float(den) else 0.0
            except (ValueError, ZeroDivisionError):
                info.fps = 0.0
            if not info.duration and st.get("duration"):
                info.duration = float(st["duration"])
        elif st.get("codec_type") == "audio" and not info.has_audio:
            info.has_audio = True
            info.acodec = st.get("codec_name")
            info.audio_rate = int(st.get("sample_rate") or 0)
            info.audio_channels = int(st.get("channels") or 0)
    if info.width and info.height and info.rotate in (90, 270):
        info.width, info.height = info.height, info.width
    return info


# ---------------------------------------------------------------------------
# decoding
# ---------------------------------------------------------------------------
def iter_frames(
    path: str | Path,
    *,
    size: tuple[int, int] | None = None,
    fps: float | None = None,
    start: float | None = None,
    duration: float | None = None,
    pix_fmt: str = "bgr24",
    extra_filters: str | None = None,
) -> Iterator[np.ndarray]:
    """Yield frames as numpy arrays (H, W, C) of the requested `size`.

    Frames are streamed through a pipe, so this works on huge files without
    ever holding more than one frame in memory.
    """
    if size is None:
        info = probe(path)
        if not info.width:
            raise ValueError(f"cannot determine video size for {path}")
        size = (info.width, info.height)
    w, h = size
    args: list[str] = [ffmpeg_exe(), "-v", "error", "-nostdin"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(path)]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    filters = []
    if fps:
        filters.append(f"fps={fps}")
    filters.append(f"scale={w}:{h}:flags=bilinear")
    if extra_filters:
        filters.append(extra_filters)
    args += ["-vf", ",".join(filters), "-f", "rawvideo", "-pix_fmt", pix_fmt, "-"]
    chan = {"bgr24": 3, "rgb24": 3, "gray": 1}[pix_fmt]
    frame_bytes = w * h * chan
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_CREATE_NO_WINDOW)
    assert proc.stdout is not None
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            arr = np.frombuffer(buf, dtype=np.uint8)
            yield arr.reshape(h, w, chan) if chan > 1 else arr.reshape(h, w)
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


def decode_audio(path: str | Path, *, rate: int = 16000, start: float | None = None,
                 duration: float | None = None) -> np.ndarray:
    """Decode any media file to mono float32 in [-1, 1] at `rate` Hz."""
    args: list[str] = [ffmpeg_exe(), "-v", "error", "-nostdin"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(path)]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    args += ["-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    proc = subprocess.run([str(a) for a in args], capture_output=True,
                          creationflags=_CREATE_NO_WINDOW)
    if proc.returncode != 0:
        raise FFmpegError(args, proc.stderr.decode("utf-8", "replace"))
    return np.frombuffer(proc.stdout, dtype=np.float32)


def write_wav(path: str | Path, audio: np.ndarray, rate: int = 16000) -> Path:
    """Write mono float32 audio to a 16-bit PCM wav (what ASR engines want)."""
    import wave

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(pcm.tobytes())
    return path


# ---------------------------------------------------------------------------
# audio analysis / loudness
# ---------------------------------------------------------------------------
def loudness(path: str | Path) -> dict:
    """EBU R128 integrated loudness via ffmpeg's ebur128 filter."""
    proc = run([ffmpeg_exe(), "-nostdin", "-i", str(path), "-filter_complex",
                "ebur128=peak=true", "-f", "null", "-"], check=False)
    text = proc.stderr or ""
    out: dict[str, float] = {}
    m = re.search(r"I:\s*(-?\d+\.?\d*)\s*LUFS", text)
    if m:
        out["integrated_lufs"] = float(m.group(1))
    m = re.search(r"LRA:\s*(-?\d+\.?\d*)\s*LU", text)
    if m:
        out["lra"] = float(m.group(1))
    peaks = re.findall(r"Peak:\s*(-?\d+\.?\d*)\s*dBFS", text)
    if peaks:
        out["true_peak_dbfs"] = float(peaks[-1])
    return out


def render(
    src: str | Path,
    dst: str | Path,
    *,
    vf: str | None = None,
    af: str | None = None,
    preset: dict | None = None,
    duration: float | None = None,
    start: float | None = None,
    quiet: bool = True,
) -> Path:
    """Encode `src` to `dst` applying optional filters and a platform preset."""
    p = preset or {}
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    args: list[str] = [ffmpeg_exe(), "-y", "-nostdin"]
    if quiet:
        args += ["-v", "error", "-stats"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    if vf:
        args += ["-vf", vf]
    if af:
        args += ["-af", af]
    args += ["-c:v", p.get("vcodec", "libx264"), "-preset", p.get("preset", "medium"),
             "-crf", str(p.get("crf", 18)), "-pix_fmt", p.get("pix_fmt", "yuv420p")]
    if p.get("profile"):
        args += ["-profile:v", p["profile"]]
    if p.get("level"):
        args += ["-level", p["level"]]
    if p.get("fps"):
        args += ["-r", str(p["fps"])]
    if p.get("max_bitrate"):
        args += ["-maxrate", str(int(p["max_bitrate"])), "-bufsize", str(int(p["max_bitrate"] * 2))]
    if af or p.get("acodec"):
        args += ["-c:a", p.get("acodec", "aac"), "-b:a", p.get("abitrate", "192k"),
                 "-ar", str(p.get("ar", 48000))]
    else:
        args += ["-an"]
    if p.get("faststart"):
        args += ["-movflags", "+faststart"]
    args += [str(dst)]
    proc = run(args, check=False)
    if proc.returncode != 0:
        raise FFmpegError(args, proc.stderr or "")
    return dst
