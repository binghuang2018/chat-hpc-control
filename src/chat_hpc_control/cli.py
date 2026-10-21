"""CLI transport; no optional model SDK imports and no implicit computation."""

import argparse
import os
from pathlib import Path
import sys
import uuid

from .contracts.codec import encode_response, parse_task
from .contracts.errors import ControlError
from .contracts.tools import ToolCall, ToolResponse


def _parser():
    parser = argparse.ArgumentParser(prog="chat-hpc-control")
    parser.add_argument("--site", type=Path, help="explicit private site TOML")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capabilities")
    commands.add_parser("github-event").add_argument("--event", type=Path, required=True)
    commands.add_parser("mcp").add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    validate = commands.add_parser("validate")
    validate.add_argument("--task", type=Path, required=True)
    validate.add_argument("--schema-only", action="store_true")
    submit = commands.add_parser("submit")
    submit.add_argument("--task", type=Path, required=True)
    submit.add_argument("--expected-manifest", required=True)
    submit.add_argument("--idempotency-key", required=True)
    submit.add_argument("--rerun-of")
    commands.add_parser("status").add_argument("run_id")
    results = commands.add_parser("results")
    results.add_argument("run_id")
    results.add_argument("--collection")
    results.add_argument("--fields", nargs="*", default=[])
    results.add_argument("--cursor")
    results.add_argument("--page-size", type=int, default=100)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("run_id")
    manifest.add_argument("--collection")
    commands.add_parser("broker").add_subparsers(dest="broker_command", required=True).add_parser("serve")
    bundle = commands.add_parser("bundle").add_subparsers(dest="bundle_command", required=True).add_parser("import")
    bundle.add_argument("archive", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate" and args.schema_only:
            task = parse_task(args.task.read_bytes())
            response = ToolResponse(str(uuid.uuid4()), True, data={
                "valid": True, "validation_level": "SCHEMA_ONLY", "task": task.to_dict()})
        else:
            if args.site is None:
                raise ControlError("SCHEMA_INVALID", "--site is required outside schema-only validation")
            from .core.config import load_site
            site = load_site(args.site)
            if args.command == "mcp":
                from .transports.mcp_server import serve_mcp
                serve_mcp(site, args.transport)
                return 0
            if args.command == "github-event":
                from .transports.github import dispatch_event
                response = dispatch_event(args.event, args.site)
                print(encode_response(response).decode())
                return 0 if response.ok else 2
            if args.command == "broker":
                if sys.platform != "linux":
                    raise ControlError("CAPABILITY_UNSUPPORTED", "native broker execution requires Linux")
                from .core.service import build_service
                from .core.rpc import serve
                serve(site, build_service(site))
                return 0
            if args.command == "bundle":
                from .contracts.auth import PeerIdentity
                from .core.auth import authorize, context_from_peer
                context = context_from_peer(PeerIdentity(os.getuid(), os.getgid(), os.getpid()), {}, site)
                authorize(context, "tasks:submit", None)
                from .sources.bundle import BundleStore
                response = ToolResponse(str(uuid.uuid4()), True, data={"bundle_id": BundleStore(site).import_tar(args.archive)})
            else:
                from .core.rpc import rpc_call
                params = {"site_id": site.site_id}
                if args.command in {"validate", "submit"}:
                    params["task"] = parse_task(args.task.read_bytes()).to_dict()
                if args.command == "submit":
                    params.update(expected_manifest_sha256=args.expected_manifest,
                                  idempotency_key=args.idempotency_key, rerun_of=args.rerun_of)
                if args.command in {"status", "results", "manifest"}:
                    params["run_id"] = args.run_id
                if args.command in {"results", "manifest"}:
                    params["collection_id"] = args.collection
                if args.command == "results":
                    params.update(fields=args.fields, cursor=args.cursor, page_size=args.page_size)
                tool = {"capabilities": "list_capabilities", "validate": "validate_task", "submit": "submit_task",
                        "status": "get_task_status", "results": "get_task_results", "manifest": "get_result_manifest"}[args.command]
                response = rpc_call(site.root / "broker.sock", ToolCall(tool, params))
    except ControlError as exc:
        response = ToolResponse(str(uuid.uuid4()), False, error=exc.to_dict())
    except OSError:
        response = ToolResponse(str(uuid.uuid4()), False, error=ControlError(
            "SCHEMA_INVALID", "input or configuration file is unavailable").to_dict())
    print(encode_response(response).decode())
    if response.ok:
        return 0
    return 3 if response.error["code"] == "BROKER_UNAVAILABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
