"""Tiny logger: readable without extra deps, quiet by default in tests."""
from __future__ import annotations

import os
import sys
import time

_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
_LEVEL = _LEVELS.get(os.environ.get("CLIPPER_LOG", "info").lower(), 20)
_T0 = time.time()


def _emit(level: str, msg: str, **fields: object) -> None:
    if _LEVELS[level] < _LEVEL:
        return
    extra = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    stamp = f"{time.time() - _T0:6.1f}s"
    tag = {"debug": "·", "info": "·", "warn": "!", "error": "×"}[level]
    line = f"[{stamp}] {tag} {msg}"
    if extra:
        line += f"  ({extra})"
    print(line, file=sys.stderr, flush=True)


def debug(msg: str, **f: object) -> None:
    _emit("debug", msg, **f)


def info(msg: str, **f: object) -> None:
    _emit("info", msg, **f)


def warn(msg: str, **f: object) -> None:
    _emit("warn", msg, **f)


def error(msg: str, **f: object) -> None:
    _emit("error", msg, **f)


class step:
    """Context manager that logs how long a named step took.

    with step("transcribe", provider="moonshine"):
        ...
    """

    def __init__(self, name: str, **fields: object) -> None:
        self.name = name
        self.fields = fields
        self.t0 = 0.0

    def __enter__(self) -> "step":
        self.t0 = time.time()
        info(f"{self.name}: start", **self.fields)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        dt = time.time() - self.t0
        if exc:
            error(f"{self.name}: failed after {dt:.1f}s", err=type(exc).__name__)
        else:
            info(f"{self.name}: done", took=f"{dt:.1f}s")
        return False
