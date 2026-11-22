"""Run-time guards shared by the stage 3 scripts (docs/PREREGISTRATION_3.md 7.4)."""

from __future__ import annotations

import re
import subprocess
import time

MIN_FREE_PERCENT = 15.0


def free_memory_percent() -> float | None:
    """System-wide free memory percentage from ``memory_pressure -Q`` (macOS); None if unavailable."""
    try:
        out = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"free percentage:\s*([0-9.]+)%", out)
    return float(m.group(1)) if m else None


def wait_for_memory(log=print, min_free: float = MIN_FREE_PERCENT, poll_s: float = 60.0) -> float:
    """Block until free memory >= ``min_free`` percent. Returns the seconds waited."""
    waited = 0.0
    while True:
        f = free_memory_percent()
        if f is None or f >= min_free:
            if waited:
                log(f"memory: resumed at {f}% free after {waited:.0f}s")
            return waited
        if waited == 0:
            log(f"memory: {f}% free < {min_free}%, waiting")
        time.sleep(poll_s)
        waited += poll_s


def code_version() -> dict:
    """Git commit of the working tree and whether tracked files differ from it (run provenance)."""
    def git(*a):
        try:
            return subprocess.run(["git", *a], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}
