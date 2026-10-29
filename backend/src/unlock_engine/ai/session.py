"""Stage A context and bounded native access for one frozen revision and target.

The session owns the immutable input package, the validated manifest, the
measured inventory and the deterministic baseline PlanResult. Construction and
verification run in fresh isolated workers; results are cached by full identity
(revision, constraints, policy, template, parameters) so a retried request can
never duplicate a CAD mutation, and a changed input can never reuse a report.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..contracts import POLICY, EngineError, Manifest, digest
from ..package import load_files
from ..planning.contracts import PlanResult, SearchPolicy
from ..planning.runner import isolated_plan
from ..worker import _run_worker, isolated_import

NATIVE_PHASES = {
    "import": 60,
    "prepare": 30,
    "constraints": 30,
    "replay": 30,
    "reverse": 30,
}


class Deadline:
    """Monotonic run deadline joined with external cancellation."""

    def __init__(
        self,
        seconds: float,
        cancel: threading.Event | None = None,
        clock=time.monotonic,
    ):
        self.clock = clock
        self.started = clock()
        self.ends = self.started + seconds
        self.external = cancel
        self.event = threading.Event()
        self._timer = threading.Timer(max(0.0, seconds), self.event.set)
        self._timer.daemon = True
        self._timer.start()
        if cancel is not None:
            self._watch = threading.Thread(target=self._relay, daemon=True)
            self._watch.start()

    def _relay(self):
        while not self.event.is_set():
            if self.external.wait(0.05):
                self.event.set()

    def remaining(self) -> float:
        return max(0.0, self.ends - self.clock())

    def elapsed(self) -> float:
        return self.clock() - self.started

    @property
    def cancelled(self) -> bool:
        return self.external is not None and self.external.is_set()

    @property
    def expired(self) -> bool:
        return self.remaining() <= 0

    def close(self):
        self._timer.cancel()
        self.event.set()


@dataclass
class EngineeringSession:
    package: object
    manifest: Manifest
    manifest_data: dict
    inventory: dict
    target_id: str
    search_policy: SearchPolicy
    baseline: PlanResult
    timings: dict = field(default_factory=dict)
    constructed: dict = field(default_factory=dict)
    verified: dict = field(default_factory=dict)

    @property
    def project_id(self) -> str:
        return self.manifest.project_id

    @property
    def revision_hash(self) -> str:
        return self.inventory["input_hash"]

    @property
    def revision_handle(self) -> str:
        return "rev_" + self.revision_hash[:16]

    @property
    def geometry_hash(self) -> str:
        return self.inventory["geometry_hash"]

    @property
    def constraint_hash(self) -> str:
        # Same identity the engine assigns to candidates (digest of the frozen manifest).
        return digest(self.manifest)

    def components(self) -> dict:
        return {c.id: c for c in self.manifest.components}

    def measured(self) -> dict:
        return {c["id"]: c for c in self.inventory["components"]}

    def binding(self, bracket_id: str):
        return next(
            (b for b in self.manifest.template_bindings if b.bracket_id == bracket_id),
            None,
        )

    # ── Stage A ──────────────────────────────────────────────────────────

    @classmethod
    def open(
        cls,
        step_bytes: bytes,
        manifest_data: dict,
        target_id: str,
        *,
        deadline: Deadline,
        search_policy: SearchPolicy = SearchPolicy(),
    ) -> "EngineeringSession":
        package = load_files(
            {
                "assembly.step": step_bytes,
                "manifest.json": json.dumps(manifest_data).encode(),
            }
        )
        manifest = Manifest.model_validate(package.manifest)
        started = time.monotonic()
        inventory = isolated_import(
            package,
            timeout_seconds=min(60, max(1, deadline.remaining())),
            cancel_event=deadline.event,
        )
        import_ms = (time.monotonic() - started) * 1000
        if not all(r.get("ok") for r in inventory["readiness"]):
            raise EngineError("UNSUPPORTED_SEMANTICS", "revision is not analysis ready")
        started = time.monotonic()
        baseline = isolated_plan(
            package,
            target_id,
            search_policy,
            expected_revision_id=inventory["input_hash"],
            cancel_event=deadline.event,
        )
        return cls(
            package=package,
            manifest=manifest,
            manifest_data=package.manifest,
            inventory=inventory,
            target_id=target_id,
            search_policy=search_policy,
            baseline=baseline,
            timings=dict(
                import_ms=import_ms, baseline_ms=(time.monotonic() - started) * 1000
            ),
        )

    # ── native work ──────────────────────────────────────────────────────

    def candidate_key(self, bracket_id: str, template_id: str, parameters: dict) -> str:
        normalized = {k: float(v) for k, v in sorted(parameters.items())}
        return digest(
            [
                self.revision_hash,
                self.constraint_hash,
                POLICY.model_dump(),
                bracket_id,
                template_id,
                normalized,
            ]
        )

    def _native(
        self,
        operation: str,
        request: dict,
        *,
        timeout_s: float,
        cancel: threading.Event,
    ) -> dict:
        with tempfile.TemporaryDirectory(prefix="unlock-ai-") as tmp:
            root = Path(tmp)
            (root / "assembly.step").write_bytes(self.package.step)
            (root / "manifest.json").write_text(
                json.dumps(self.package.manifest, allow_nan=False)
            )
            (root / "request.json").write_text(
                json.dumps(
                    dict(expected_revision_hash=self.revision_hash, **request),
                    allow_nan=False,
                )
            )
            limits = dict(NATIVE_PHASES, search=self.search_policy.max_seconds)
            return _run_worker(root, operation, timeout_s, cancel, phase_limits=limits)

    def construct(
        self, template: dict, *, timeout_s: float, cancel: threading.Event
    ) -> tuple[dict, bool]:
        """Returns (result, cached). Idempotent by full candidate identity."""
        key = self.candidate_key(**template)
        if key in self.constructed:
            return self.constructed[key], True
        started = time.monotonic()
        try:
            result = self._native(
                "ai_construct",
                dict(template=template),
                timeout_s=min(30, timeout_s),
                cancel=cancel,
            )
        except EngineError as exc:
            # Worker timeout, crash or cancellation: no completed geometry. Not cached.
            return dict(
                ok=False,
                error=exc.envelope(),
                interrupted=True,
                wall_ms=(time.monotonic() - started) * 1000,
            ), False
        result["wall_ms"] = (time.monotonic() - started) * 1000
        self.constructed[key] = result
        return result, False

    def verify(
        self,
        template: dict,
        candidate_id: str,
        *,
        timeout_s: float,
        cancel: threading.Event,
    ) -> tuple[dict, bool]:
        if candidate_id in self.verified:
            return self.verified[candidate_id], True
        started = time.monotonic()
        request = dict(
            template=template,
            expected_candidate_id=candidate_id,
            target_id=self.target_id,
            search_policy=self.search_policy.model_dump(mode="json"),
        )
        try:
            result = self._native(
                "ai_verify", request, timeout_s=min(150, timeout_s), cancel=cancel
            )
        except EngineError as exc:
            return dict(
                ok=False,
                error=exc.envelope(),
                interrupted=True,
                wall_ms=(time.monotonic() - started) * 1000,
            ), False
        result["wall_ms"] = (time.monotonic() - started) * 1000
        if result.get("plan") is not None:
            result["plan"] = PlanResult.model_validate(result["plan"])
        self.verified[candidate_id] = result
        return result, False
