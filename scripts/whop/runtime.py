"""Where the pipeline finds its interpreter and its libraries.

Two hardcodes were stopping the chain from running anywhere but the machine it
was written on:

* `ROOT / "python"` — a path that exists on the author's box and not
  in this sandbox, which has `venv/`. A subprocess that names an interpreter by
  directory is a subprocess that only works on one computer.
* `LD_LIBRARY_PATH=/tmp/al2023/lib` — the ALSA runtime for the renderer on one
  particular distro. Set unconditionally, it is at best ignored and at worst it
  shadows the system libraries with a partial copy.

Both are now looked up instead of assumed: the interpreter is whatever is
running the script (`sys.executable`), and the library path is only exported
when the directory is actually there.

    from scripts.whop import runtime
    runtime.python_exe()      -> the interpreter to hand to subprocess
    runtime.render_env()      -> os.environ with the ALSA path if it exists
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The ALSA runtime the renderer wants on some distros. Optional by definition:
# it is a fix for one environment, not a requirement of the pipeline.
ALSA_LIB = Path("/tmp/al2023/lib")

# Everything the whop chain imports, mapped to the name you pip install for it.
NEEDED = {
    "numpy": "numpy",
    "PIL": "pillow",
    "cv2": "opencv-python-headless",
    "jsonschema": "jsonschema",
}


def python_exe() -> str:
    """The interpreter running right now — the only one guaranteed to exist.

    A venv is not a fixed directory name. Using `sys.executable` means the
    chain works in `venv/`, `.venv/`, a system python, or CI, without a config
    flag and without silently falling back to a different interpreter that
    lacks the packages.
    """
    return sys.executable


def render_env(base: dict | None = None) -> dict:
    """os.environ, plus the ALSA path only when that path exists."""
    env = dict(os.environ if base is None else base)
    if ALSA_LIB.is_dir():
        env["LD_LIBRARY_PATH"] = str(ALSA_LIB)
    else:
        # Do not leave a stale value pointing at a directory that is not there:
        # the dynamic loader treats a missing entry as a fatal error for some
        # binaries rather than skipping it.
        env.pop("LD_LIBRARY_PATH", None)
    return env


def missing_deps() -> list[tuple[str, str]]:
    """[(import name, pip name)] for everything not importable here."""
    out = []
    for mod, pip_name in NEEDED.items():
        try:
            importlib.import_module(mod)
        except Exception:
            out.append((mod, pip_name))
    return out


def describe_env() -> list[str]:
    """A short, honest report of this interpreter."""
    lines = [f"python      {sys.executable}",
             f"version     {sys.version.split()[0]}"]
    deps = missing_deps()
    if deps:
        lines.append("missing     " + ", ".join(m for m, _ in deps))
        lines.append("install     " + " ".join(f"pip install {p}" for _, p in deps))
    else:
        lines.append("missing     nothing")
    lines.append(f"alsa lib    {ALSA_LIB}"
                 + ("  (found)" if ALSA_LIB.is_dir() else "  (absent — fine)"))
    return lines
