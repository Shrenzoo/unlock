"""Immutable byte artifacts; partial work never receives a completed bundle record."""

import hashlib
import json
import os
from pathlib import Path
import tempfile

from .contracts import EngineError


def atomic_write(path: Path, data: bytes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes):
        key = hashlib.sha256(data).hexdigest()
        path = self.root / key[:2] / key
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            if path.read_bytes() != data:
                raise EngineError(
                    "GEOMETRY_FAILED", "content-addressed artifact corrupted"
                )
        else:
            # Hard link provides atomic create-if-absent, including concurrent writers.
            fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.link(tmp, path)
                except FileExistsError:
                    if path.read_bytes() != data:
                        raise EngineError(
                            "GEOMETRY_FAILED", "concurrent artifact corruption"
                        )
            finally:
                os.unlink(tmp)
        return key

    def get(self, key: str):
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise EngineError("NOT_FOUND", "invalid artifact ID")
        data = (self.root / key[:2] / key).read_bytes()
        if hashlib.sha256(data).hexdigest() != key:
            raise EngineError("GEOMETRY_FAILED", "artifact hash mismatch")
        return data

    def put_json(self, value):
        return self.put(
            json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode()
        )
