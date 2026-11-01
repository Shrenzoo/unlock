"""Durable immutable JSON snapshots, never a writable SQLite file on shared storage."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from ..artifacts import ArtifactStore, atomic_write
from ..contracts import EngineError
from ..api.views import revision_view

MAX_JOB_BYTES = 256 * 1024**2
MAX_STORAGE_BYTES = 1024**3


def storage_size(root):
    return sum(p.stat().st_size for p in Path(root).rglob("*") if p.is_file())


def save_snapshot(coordinator, destination: Path, *, run_id=None):
    """Publish only committed records, evidence and hash-checked artifact bytes."""
    store = coordinator.store
    with store.lock:
        records = [
            dict(row)
            for row in store.db.execute(
                "SELECT id,kind,data FROM records ORDER BY rowid"
            )
        ]
        events = [
            dict(row)
            for row in store.db.execute(
                "SELECT job_id,sequence,data FROM events ORDER BY job_id,sequence"
            )
        ]
    payload = dict(
        version=1,
        provider=coordinator.config.public(),
        demo_run_id=run_id,
        records=[dict(row, data=json.loads(row["data"])) for row in records],
        events=[dict(row, data=json.loads(row["data"])) for row in events],
    )
    encoded = json.dumps(payload, allow_nan=False).encode()
    if storage_size(store.artifacts.root) + len(encoded) > MAX_JOB_BYTES:
        raise EngineError("LIMIT_EXCEEDED", "job artifact storage limit exceeded")
    destination.mkdir(parents=True, exist_ok=True)
    # Each job owns its destination. The caller serializes cloud writers.
    target = ArtifactStore(destination / "artifacts")
    for p in store.artifacts.root.glob("*/*"):
        if len(p.name) == 64 and all(c in "0123456789abcdef" for c in p.name):
            target.put(store.artifacts.get(p.name))
    atomic_write(destination / "snapshot.json", encoded)


def compose_gallery(sources, destination: Path):
    """Merge completed fixture jobs into one snapshot; bytes are re-hashed on copy."""
    records, events, demo_runs, members, provider = {}, [], {}, [], None
    destination = Path(destination)
    target = ArtifactStore(destination / "artifacts")
    for source in map(Path, sources):
        status = json.loads((source / "status.json").read_bytes())
        if status.get("state") != "completed" or not status.get("fixture"):
            raise ValueError(f"{source.name} is not a completed fixture job")
        store = SnapshotStore(source)
        if provider is not None and store.data["provider"] != provider:
            raise ValueError("gallery jobs used different decision policies")
        provider = store.data["provider"]
        for row in store.data["records"]:
            if records.setdefault(row["id"], row) != row:
                raise ValueError(f"conflicting record {row['id']}")
        events.extend(store.data["events"])
        run = store.get("run", status["run_id"])
        project = store.get("revision", run["revision_id"])["project_id"]
        if project in demo_runs:
            raise ValueError(f"{project} appears in more than one job")
        demo_runs[project] = run["id"]
        for p in (source / "artifacts").glob("*/*"):
            target.put(store.artifacts.get(p.name))
        members.append(status)
        records[project]["data"]["outcome"] = run["outcome"]
    payload = dict(
        version=1,
        provider=provider,
        demo_run_id=demo_runs.get("fixture_B02"),
        demo_runs=demo_runs,
        records=list(records.values()),
        events=events,
    )
    atomic_write(
        destination / "snapshot.json", json.dumps(payload, allow_nan=False).encode()
    )
    atomic_write(
        destination / "gallery.json",
        json.dumps(dict(members=members), indent=2).encode(),
    )
    return demo_runs


class SnapshotStore:
    def __init__(self, root):
        root = Path(root)
        encoded = (root / "snapshot.json").read_bytes()
        if len(encoded) > MAX_JOB_BYTES:
            raise ValueError("snapshot is too large")
        self.data = json.loads(encoded)
        if self.data["version"] != 1:
            raise ValueError("unsupported snapshot version")
        self.records = {(r["kind"], r["id"]): r["data"] for r in self.data["records"]}
        self.artifacts = ArtifactStore.__new__(ArtifactStore)
        self.artifacts.root = (
            root / "artifacts"
        )  # read-only Volume: never mkdir or write

    def get(self, kind, id):
        try:
            return json.loads(json.dumps(self.records[kind, id]))
        except KeyError:
            raise EngineError("NOT_FOUND", f"{kind} not found") from None

    def list(self, kind):
        return [self.get(k, id) for k, id in self.records if k == kind]

    def events(self, job_id, after=0):
        return [
            r["data"]
            for r in self.data["events"]
            if r["job_id"] == job_id and r["sequence"] > after
        ]


class RequestLimiter:
    """Global per-container ceilings, independent of spoofable forwarding headers."""

    def __init__(self, per_minute=120, per_hour=720, clock=time.monotonic):
        self.clock, self.per_minute, self.per_hour = clock, per_minute, per_hour
        self.requests = deque()
        self.lock = threading.Lock()

    def allow(self):
        with self.lock:
            now = self.clock()
            while self.requests and self.requests[0] <= now - 3600:
                self.requests.popleft()
            if (
                len(self.requests) >= self.per_hour
                or sum(t > now - 60 for t in self.requests) >= self.per_minute
            ):
                return False
            self.requests.append(now)
            return True


class SnapshotCoordinator:
    def run_view(self, id):
        record = self.store.get("run", id)
        record["events"] = [
            event
            for job in self.store.list("job")
            if job["run_id"] == id
            for event in self.store.events(job["id"])
        ]
        return {k: v for k, v in record.items() if k != "baseline_artifact"}

    def revision_view(self, id):
        return revision_view(self.store.get("revision", id))

    def __init__(self, root):
        self.store = SnapshotStore(root)
        self.demo_run_id = self.store.data["demo_run_id"]
        # A single-job snapshot predates the gallery; its one run opens its project.
        self.demo_runs = self.store.data.get("demo_runs") or (
            {
                self.store.get(
                    "revision", self.store.get("run", self.demo_run_id)["revision_id"]
                )["project_id"]: self.demo_run_id
            }
            if self.demo_run_id
            else {}
        )
        provider = self.store.data["provider"]
        self.config = SimpleNamespace(public=lambda: dict(provider))
        self.limiter = RequestLimiter()

    def close(self):
        pass


def create_snapshot_app(root, *, allowed_hosts=None):
    from ..api.app import create_app

    return create_app(
        root=root,
        seed=False,
        coordinator_factory=SnapshotCoordinator,
        read_only=True,
        allowed_hosts=allowed_hosts,
    )
