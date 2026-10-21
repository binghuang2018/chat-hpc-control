"""One plugin operation per isolated interpreter, never a model shell."""

import argparse
from contextlib import redirect_stdout
from dataclasses import replace
import json
import sys

from ..contracts.codec import decode_json, validate_schema
from ..contracts.config import RuntimeConfig
from ..contracts.errors import ControlError
from ..contracts.plugins import PluginInfo, PrepareContext, ValidationContext
from ..contracts.results import OutputSnapshot
from ..contracts.task import FrozenTask, ResolvedTask
from .discovery import distribution_digest, installed_entries, normalized
from .wire import from_wire, to_wire


def main():
    parser = argparse.ArgumentParser()
    for key in ("engine-id", "distribution", "entry-point", "code-sha256"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    try:
        limit = 256 * 1024 * 1024
        request = decode_json(sys.stdin.buffer.read(limit + 1), max_bytes=limit)
        validate_schema("plugin-rpc-v1", request)
        if request["engine_id"] != args.engine_id:
            raise ControlError("PLUGIN_INCOMPATIBLE", "plugin identity mismatch")
        entries = [e for e in installed_entries() if e.name == args.engine_id
                   and normalized(e.dist.metadata["Name"]) == args.distribution
                   and e.value == args.entry_point]
        if len(entries) != 1 or distribution_digest(entries[0].dist) != args.code_sha256:
            raise ControlError("PLUGIN_INCOMPATIBLE", "installed distribution changed before load")
        with redirect_stdout(sys.stderr):
            plugin = entries[0].load()()
            info = plugin.info()
            if (not isinstance(info, PluginInfo) or info.engine_id != args.engine_id
                    or info.api_version.split(".")[0] != "1"):
                raise ControlError("PLUGIN_INCOMPATIBLE", "plugin API or engine identity mismatch")
            info = replace(info, distribution=args.distribution, version=entries[0].dist.version,
                           code_sha256=args.code_sha256)
            data = request["request"]
            method = request["method"]
            if method == "info":
                if data:
                    raise ControlError("SCHEMA_INVALID", "info accepts no parameters")
                value = info
            elif method == "probe":
                if set(data) != {"site_runtime"}:
                    raise ControlError("SCHEMA_INVALID", "invalid probe parameters")
                value = plugin.probe(from_wire(data["site_runtime"], RuntimeConfig))
            elif method == "validate":
                if set(data) != {"task", "context"}:
                    raise ControlError("SCHEMA_INVALID", "invalid validation parameters")
                value = plugin.validate(from_wire(data["task"], ResolvedTask),
                                        from_wire(data["context"], ValidationContext))
            elif method == "prepare":
                if set(data) != {"task", "context"}:
                    raise ControlError("SCHEMA_INVALID", "invalid prepare parameters")
                value = plugin.prepare(from_wire(data["task"], FrozenTask),
                                       from_wire(data["context"], PrepareContext))
            else:
                if set(data) != {"snapshot", "contract"}:
                    raise ControlError("SCHEMA_INVALID", "invalid parse parameters")
                value = plugin.parse(from_wire(data["snapshot"], OutputSnapshot), data["contract"])
        response = {"ok": True, "result": to_wire(value)}
    except ControlError as exc:
        response = {"ok": False, "error": exc.to_dict()}
    except Exception:
        response = {"ok": False, "error": ControlError(
            "PLUGIN_INCOMPATIBLE", "installed plugin operation failed").to_dict()}
    print(json.dumps(response, allow_nan=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
