"""Versioned plan file with optimistic concurrency. Standard library only (POSIX flock).

Keep the file on local disk (``/var/lib/a3/th`` in the container): flock is not reliable
on network or FUSE mounts.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path


class VersionConflict(Exception):
    """The plan changed since the caller read it; re-read and retry."""


def default_plan_path() -> Path:
    return Path(os.environ.get("TH_STATE_DIR", "~/.th-state")).expanduser() / "plan.json"


class PlanStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_plan_path()
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 0, "days": []}

    def write(self, plan: dict, expected_version: int) -> int:
        """Write ``plan`` if the stored version is still ``expected_version``; return the new one."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                current = int(self.read().get("version", 0))
                if current != expected_version:
                    raise VersionConflict(f"plan version is {current}, expected {expected_version}")
                new_version = current + 1
                body = {**{k: v for k, v in plan.items() if k != "version"}, "version": new_version}
                tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
                tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
                os.replace(tmp, self.path)
                return new_version
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
