"""The six public tools share one broker and one authorization policy."""

from dataclasses import asdict
from importlib.resources import files
import json
import uuid

from jsonschema import Draft202012Validator

from ..contracts.auth import CallContext
from ..contracts.codec import parse_task
from ..contracts.errors import ControlError
from ..contracts.execution import SubmissionRequest
from ..contracts.results import ResultPage
from ..contracts.tools import ToolCall, ToolResponse
from .auth import authorize, authorize_run


def tool_definitions() -> list[dict]:
    string = {"type": "string", "minLength": 1}
    nullable = {"type": ["string", "null"]}
    task = json.loads(files("chat_hpc_control").joinpath("schemas/task-v1.json").read_text())
    specs = {
        "list_capabilities": ({"site_id": string}, True, "Read the site's enabled engines and resource policy."),
        "validate_task": ({"site_id": string, "task": task}, True, "Validate and pin inputs without registering or submitting a job."),
        "submit_task": ({"site_id": string, "task": task,
                         "expected_manifest_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                         "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128},
                         "rerun_of": nullable}, False, "Submit one authorized immutable task; retries must preserve the intent key."),
        "get_task_status": ({"site_id": string, "run_id": string}, True, "Read observed execution state, not scientific acceptance."),
        "get_task_results": ({"site_id": string, "run_id": string, "collection_id": nullable,
                              "fields": {"type": "array", "uniqueItems": True, "items": {"enum": [
                                  "record_id", "energy", "gradient", "atom_symbols", "geometry", "geometry_unit",
                                  "charge", "multiplicity", "method", "basis", "state_id", "units", "provenance",
                                  "converged", "evidence_level"]}},
                              "cursor": nullable, "page_size": {"type": "integer", "minimum": 1, "maximum": 100}},
                             True, "Read a page pinned to one immutable result collection."),
        "get_result_manifest": ({"site_id": string, "run_id": string, "collection_id": nullable},
                                True, "Read authorized raw-file identities and availability."),
    }
    return [{"name": name, "description": description, "readOnlyHint": readonly,
             "inputSchema": {"type": "object", "properties": props, "required": list(props),
                             "additionalProperties": False}}
            for name, (props, readonly, description) in specs.items()]


class PendingResultReader:
    def __init__(self, store):
        self.store = store

    def _row(self, run_id, context):
        authorize(context, "results:read", None)
        row = self.store.get_run(run_id)
        authorize_run(context, row["owner"], row["site_id"], "results:read")
        return row

    def get_page(self, run_id, collection_id, fields, cursor, page_size, context):
        row = self._row(run_id, context)
        if collection_id is not None or cursor is not None:
            raise ControlError("RESULT_UNVERIFIED", "requested collection is not available")
        return ResultPage(None, [], None, {"collection_state": "PENDING", "data_ready": False,
                          "execution_state": row["execution_state"], "completeness": "UNVERIFIED",
                          "scientific_acceptance": "NOT_EVALUATED"})

    def get_manifest(self, run_id, collection_id, context):
        self._row(run_id, context)
        if collection_id is not None:
            raise ControlError("RESULT_UNVERIFIED", "requested collection is not available")
        return {"run_id": run_id, "collection_id": None, "collection_state": "PENDING", "files": []}


class ToolService:
    def __init__(self, broker, reader=None):
        self.broker = broker
        self.reader = reader or PendingResultReader(broker.store)
        self.definitions = {t["name"]: t for t in tool_definitions()}

    def handle(self, call: ToolCall, context: CallContext) -> ToolResponse:
        request_id = str(uuid.uuid4())
        try:
            if call.name not in self.definitions:
                raise ControlError("SCHEMA_INVALID", "unknown public tool")
            schema = self.definitions[call.name]["inputSchema"]
            if next(Draft202012Validator(schema).iter_errors(call.arguments), None):
                raise ControlError("SCHEMA_INVALID", "tool parameters violate their schema")
            args = call.arguments
            if args["site_id"] != context.site_id or args["site_id"] != self.broker.site.site_id:
                raise ControlError("AUTH_DENIED", "tool targets another site")
            if call.name == "list_capabilities":
                authorize(context, "capabilities:read", None)
                engines = []
                for engine_id, plugin in self.broker.engines.items():
                    if engine_id not in context.engines and "*" not in context.engines:
                        continue
                    info = plugin.info()
                    probe = plugin.probe(self.broker.site.engines[engine_id])
                    engines.append({"engine_id": engine_id, "available": probe.available,
                                    "version": probe.version, "profiles": list(info.profiles),
                                    "plugin_version": info.version, "options_schema": info.options_schema})
                data = {"site_id": context.site_id, "engines": engines,
                        "executor": asdict(self.broker.executor.probe(self.broker.site.executor))}
            elif call.name == "validate_task":
                report = self.broker.validate(parse_task(json.dumps(args["task"]).encode()), context)
                data = {"valid": report.valid, "task": report.task.to_dict() if report.task else None,
                        "manifest_sha256": report.manifest_sha256, "issues": list(report.issues)}
            elif call.name == "submit_task":
                task = parse_task(json.dumps(args["task"]).encode())
                receipt = self.broker.submit(SubmissionRequest(
                    args["site_id"], task, args["expected_manifest_sha256"],
                    args["idempotency_key"], args["rerun_of"]), context)
                data = {"run_id": receipt.run_id, "reservation_id": receipt.reservation_id,
                        "execution_state": receipt.execution_state,
                        "task_ref": {"site_id": context.site_id, "task_id": task.task_id,
                                     "manifest_sha256": args["expected_manifest_sha256"]}}
            elif call.name == "get_task_status":
                data = asdict(self.broker.get_status(args["run_id"], context))
            elif call.name == "get_task_results":
                authorize(context, "results:read", None)
                data = asdict(self.reader.get_page(args["run_id"], args["collection_id"], args["fields"],
                                                  args["cursor"], args["page_size"], context))
            else:
                authorize(context, "results:read", None)
                data = self.reader.get_manifest(args["run_id"], args["collection_id"], context)
            return ToolResponse(request_id, True, data=data)
        except ControlError as exc:
            return ToolResponse(request_id, False, error=exc.to_dict())
        except Exception:
            return ToolResponse(request_id, False, error=ControlError(
                "INTERNAL_ERROR", "tool could not be completed; no retry with a new intent key").to_dict())


def build_service(site):
    """Assemble only operator-enabled installed engines and an explicit executor."""
    from .broker import Broker
    from .store import StateStore
    from ..sources.base import SourceResolver
    from ..plugins.discovery import discover_enabled
    from ..plugins.host import EngineProxy, PluginHost
    from ..executors.loader import load_executor
    executor = load_executor(site)
    store = StateStore.open(site.root)
    try:
        descriptors = discover_enabled(site)
        if set(site.engines) - descriptors.keys():
            raise ControlError("CAPABILITY_UNSUPPORTED", "configured engine distribution is not installed")
        host = PluginHost(site)
        engines = {name: EngineProxy(host, name) for name in descriptors}
        return ToolService(Broker(site, store, SourceResolver(), engines, executor))
    except Exception:
        store.close()
        raise
