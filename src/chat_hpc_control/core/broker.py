"""The sole path from an authenticated task to a durable native submission."""

from dataclasses import asdict
import hashlib
from pathlib import Path
import re
import threading

from jsonschema import Draft202012Validator

from ..contracts.auth import CallContext
from ..contracts.config import SiteConfig
from ..contracts.errors import ControlError
from ..contracts.execution import ApprovedExecutionPlan, SubmissionRequest
from ..contracts.plugins import PrepareContext, ValidationContext, ValidationReport
from ..contracts.results import RunStatus
from ..contracts.task import TaskSpec
from .auth import authorize, authorize_run
from .manifest import build_manifest, canonical_bytes, freeze
from .resources import validate_resources
from .store import StateStore


class Broker:
    def __init__(self, site: SiteConfig, store: StateStore, resolver, engines: dict, executor):
        self.site, self.store, self.resolver = site, store, resolver
        self.engines, self.executor = engines, executor
        self._submit_lock = threading.RLock()

    def _site(self, context):
        if context.site_id != self.site.site_id:
            raise ControlError("AUTH_DENIED", "caller belongs to another site")

    def _prepare(self, task: TaskSpec):
        if task.engine_id not in self.engines or task.engine_id not in self.site.engines:
            raise ControlError("CAPABILITY_UNSUPPORTED", "engine is not enabled at this site")
        engine = self.engines[task.engine_id]
        info = engine.info()
        if info.engine_id != task.engine_id or info.api_version.split(".")[0] != "1":
            raise ControlError("PLUGIN_INCOMPATIBLE", "engine identity or API is incompatible")
        Draft202012Validator.check_schema(info.options_schema)
        if next(Draft202012Validator(info.options_schema).iter_errors(task.engine_options), None):
            raise ControlError("SCHEMA_INVALID", "engine options violate the installed plugin schema")
        validate_resources(task.resources, self.executor.probe(self.site.executor))
        resolved = self.resolver.resolve(task, self.site)
        report = engine.validate(resolved, ValidationContext(self.site))
        if not report.valid:
            raise ControlError("SCHEMA_INVALID", "native input validation failed")
        probe = engine.probe(self.site.engines[task.engine_id])
        if not probe.available:
            raise ControlError("CAPABILITY_UNSUPPORTED", "native runtime is unavailable")
        manifest = build_manifest(resolved, info, probe, self.site)
        digest = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
        return resolved, manifest, digest

    def validate(self, task: TaskSpec, context: CallContext) -> ValidationReport:
        self._site(context)
        authorize(context, "tasks:validate", task)
        resolved, manifest, digest = self._prepare(task)
        return ValidationReport(True, resolved.task, digest, manifest)

    def submit(self, request: SubmissionRequest, context: CallContext):
        self._site(context)
        authorize(context, "tasks:submit", request.task)
        if request.site_id != self.site.site_id:
            raise ControlError("AUTH_DENIED", "submission targets another site")
        if (not re.fullmatch(r"[0-9a-f]{64}", request.expected_manifest_sha256)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:#/-]{0,127}", request.idempotency_key)):
            raise ControlError("SCHEMA_INVALID", "invalid manifest digest or idempotency key")
        with self._submit_lock:
            old = self.store.find_key(request.site_id, context.principal, request.idempotency_key)
            if old:
                if canonical_bytes(old.request) != canonical_bytes(asdict(request)):
                    raise ControlError("IDEMPOTENCY_CONFLICT", "key already identifies another request")
                return self.store.get_receipt(old)
            if request.rerun_of:
                previous = self.store.get_run(request.rerun_of)
                authorize_run(context, previous["owner"], previous["site_id"], "tasks:submit")
            if (request.task.source["kind"] == "git"
                    and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", request.task.source["ref"])):
                raise ControlError("INPUT_CHANGED", "submit must use validate's fixed commit")
            resolved, manifest, digest = self._prepare(request.task)
            if digest != request.expected_manifest_sha256:
                raise ControlError("INPUT_CHANGED", "source, runtime or site policy changed after validate")
            frozen = freeze(resolved, self.site, manifest=manifest)
            fingerprint = hashlib.sha256(canonical_bytes({
                "manifest_sha256": digest, "site_id": self.site.site_id,
                "executor_id": self.site.executor.identity})).hexdigest()
            reservation = self.store.reserve(request, context, fingerprint)
            run_root = self.site.root / "runs" / reservation.run_id
            run_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                plan = self.engines[request.task.engine_id].prepare(
                    frozen, PrepareContext(self.site, run_root, self.site.engines[request.task.engine_id]))
                from ..sources.base import checked_paths
                checked_paths([name for name in plan.outputs if name != "*"])
                if plan.engine_id != request.task.engine_id:
                    raise ControlError("SCHEMA_INVALID", "engine returned an unrelated execution plan")
                runtime = self.site.engines[request.task.engine_id]
                trusted_executables = {Path(runtime.executable).resolve()}
                if runtime.mpi_argv and Path(runtime.mpi_argv[0]).is_absolute():
                    trusted_executables.add(Path(runtime.mpi_argv[0]).resolve())
                if (not plan.argv or not all(isinstance(a, str) and "\x00" not in a for a in plan.argv)
                        or not Path(plan.argv[0]).is_absolute()
                        or Path(plan.argv[0]).resolve() not in trusted_executables
                        or not plan.cwd.resolve().is_relative_to(run_root.resolve())
                        or plan.resources != request.task.resources):
                    raise ControlError("SCHEMA_INVALID", "unapproved execution plan")
            except Exception:
                self.store.update_state(reservation.reservation_id, "FAILED", {"reason": "PLAN_REJECTED"})
                raise
            approved = ApprovedExecutionPlan(plan, self.site.site_id, reservation.run_id, digest, frozen.input_root)
            try:
                receipt = self.executor.submit(approved, reservation.reservation_id)
                if (receipt.handle and (receipt.handle.executor_id != self.executor.info().executor_id
                                       or receipt.handle.run_root != str(run_root))):
                    raise ControlError("JOB_IDENTITY_UNVERIFIED", "executor returned an unrelated handle")
                self.store.record_receipt(reservation, receipt)
            except Exception as exc:
                existing = self.store.get_receipt(reservation)
                if existing.handle is not None:
                    return existing
                self.store.update_state(reservation.reservation_id, "SUBMISSION_UNKNOWN",
                                        {"reason": "SUBMISSION_OUTCOME_UNCONFIRMED"})
                raise ControlError("SUBMISSION_UNKNOWN", "native submission may exist; reconcile before retry",
                                   retryable=True, evidence_refs=[reservation.reservation_id]) from exc
            return receipt

    def get_status(self, run_id: str, context: CallContext) -> RunStatus:
        self._site(context)
        authorize(context, "tasks:read", None)
        row = self.store.get_run(run_id)
        authorize_run(context, row["owner"], row["site_id"], "tasks:read")
        return RunStatus(run_id, row["execution_state"], row["observed_at"],
                         collection_state=row["evidence"].get("collection_state", "PENDING"),
                         publication_state=row["evidence"].get("publication_state", "NOT_REQUESTED"), evidence=row["evidence"])
