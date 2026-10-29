"""SQLite coordination records plus immutable content-addressed artifacts."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from ..artifacts import ArtifactStore
from ..contracts import EngineError


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts = ArtifactStore(self.root / "artifacts")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "unlock.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS records (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL,
          parent_id TEXT REFERENCES records(id), data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS records_kind ON records(kind);
        CREATE TABLE IF NOT EXISTS events (
          job_id TEXT NOT NULL REFERENCES records(id), sequence INTEGER NOT NULL,
          data TEXT NOT NULL, PRIMARY KEY(job_id,sequence));
        CREATE TABLE IF NOT EXISTS idempotency (
          scope TEXT NOT NULL, key TEXT NOT NULL, input_hash TEXT NOT NULL,
          response TEXT NOT NULL, PRIMARY KEY(scope,key));
        """)
        self.db.commit()
        for job in self.list("job"):
            if job["state"] in ("queued", "running"):
                job.update(
                    state="interrupted",
                    error=dict(
                        error_code="GEOMETRY_FAILED",
                        message="Coordinator restarted before completion",
                        retryable=True,
                        field_errors=[],
                        evidence_ids=[],
                        run_id=job.get("run_id"),
                    ),
                )
                self.put("job", job["id"], job, job.get("run_id"))
                self.event(
                    job["id"],
                    dict(
                        stage="inspect",
                        state="failed",
                        message="Job interrupted by restart",
                        t_ms=0,
                        terminal=True,
                    ),
                )

    def put(self, kind, id, data, parent=None, *, immutable=False):
        encoded = json.dumps(data, allow_nan=False, separators=(",", ":"))
        with self.lock, self.db:
            old = self.db.execute(
                "SELECT kind,data FROM records WHERE id=?", (id,)
            ).fetchone()
            if old and (
                old["kind"] != kind or (immutable and json.loads(old["data"]) != data)
            ):
                raise EngineError(
                    "STALE_REVISION", "immutable record identity conflict"
                )
            self.db.execute(
                "INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (id, kind, parent, encoded),
            )

    def get(self, kind, id):
        with self.lock:
            row = self.db.execute(
                "SELECT data FROM records WHERE id=? AND kind=?", (id, kind)
            ).fetchone()
        if row is None:
            raise EngineError("NOT_FOUND", f"{kind} not found")
        return json.loads(row["data"])

    def list(self, kind):
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM records WHERE kind=? ORDER BY rowid", (kind,)
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def event(self, job_id, data):
        with self.lock, self.db:
            seq = self.db.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE job_id=?",
                (job_id,),
            ).fetchone()[0]
            event = dict(data, sequence=seq)
            self.db.execute(
                "INSERT INTO events VALUES (?,?,?)",
                (job_id, seq, json.dumps(event, allow_nan=False)),
            )
        return event

    def events(self, job_id, after=0):
        with self.lock:
            rows = self.db.execute(
                "SELECT data FROM events WHERE job_id=? AND sequence>? ORDER BY sequence",
                (job_id, after),
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def idem(self, scope, key, input_hash, response=None):
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT input_hash,response FROM idempotency WHERE scope=? AND key=?",
                (scope, key),
            ).fetchone()
            if row:
                if row["input_hash"] != input_hash:
                    raise EngineError(
                        "STALE_REVISION",
                        "idempotency key was reused with different input",
                    )
                return json.loads(row["response"])
            if response is not None:
                self.db.execute(
                    "INSERT INTO idempotency VALUES (?,?,?,?)",
                    (scope, key, input_hash, json.dumps(response)),
                )
        return response
