"""Bounded plugin subprocesses, with clean environments and typed responses."""

from dataclasses import replace
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time

from ..contracts.codec import decode_json, validate_schema
from ..contracts.config import ExecutorConfig, SiteConfig
from ..contracts.errors import ControlError
from ..contracts.execution import ExecutionPlan
from ..contracts.plugins import PluginInfo, ProbeReport, ValidationReport
from ..contracts.results import ParseReport
from .discovery import discover_enabled
from .wire import from_wire, to_wire


def _private_site(site: SiteConfig, engine_id: str) -> SiteConfig:
    return replace(site, principals={}, repositories={}, gateway_uids=(), local_principals={},
                   engines={engine_id: site.engines[engine_id]},
                   executor=ExecutorConfig(site.executor.kind, site.executor.identity),
                   settings={k: v for k, v in site.settings.items() if k in {"geometry_tolerance"}})


def _bounded_process(argv, data, environment, cwd, timeout, limit):
    with tempfile.TemporaryFile() as input_stream:
        input_stream.write(data)
        input_stream.seek(0)
        process = subprocess.Popen(argv, stdin=input_stream, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=environment, cwd=cwd,
                                   start_new_session=True, close_fds=True)
        output = bytearray()
        total = 0
        deadline = time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                selector.register(process.stderr, selectors.EVENT_READ, "stderr")
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ControlError("PLUGIN_INCOMPATIBLE", "plugin control call timed out")
                    for key, _ in selector.select(min(remaining, .1)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        if total > limit:
                            raise ControlError("PLUGIN_INCOMPATIBLE", "plugin response exceeds its byte bound")
                        if key.data == "stdout":
                            output.extend(chunk)
            process.wait(timeout=max(.1, deadline - time.monotonic()))
            if process.returncode:
                raise ControlError("PLUGIN_INCOMPATIBLE", "plugin process did not finish successfully")
            return bytes(output)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            process.stdout.close()
            process.stderr.close()


class PluginHost:
    def __init__(self, site: SiteConfig):
        self.site = site

    def call(self, engine_id: str, method: str, request: dict) -> dict:
        envelope = {"schema": "chat-hpc-control/plugin-rpc/v1", "engine_id": engine_id,
                    "method": method, "request": request}
        validate_schema("plugin-rpc-v1", envelope)
        descriptors = discover_enabled(self.site)
        if engine_id not in descriptors:
            raise ControlError("CAPABILITY_UNSUPPORTED", "engine plugin is not enabled and installed")
        descriptor = descriptors[engine_id]
        data = json.dumps(envelope, allow_nan=False, separators=(",", ":")).encode()
        limit = self.site.settings.get("plugin_rpc_max_bytes", 128 * 1024 * 1024)
        if type(limit) is not int or limit <= 0 or len(data) > limit:
            raise ControlError("PLUGIN_INCOMPATIBLE", "plugin input exceeds its byte bound")
        timeout = self.site.settings.get("plugin_control_timeout_seconds", 30)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ControlError("SCHEMA_INVALID", "plugin control timeout must be finite and positive")
        home = self.site.root / "plugin-home"
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
        env = {"PATH": os.defpath, "HOME": str(home), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        argv = [sys.executable, "-I", "-B", "-m", "chat_hpc_control.plugins.worker_main",
                "--engine-id", descriptor.engine_id, "--distribution", descriptor.distribution,
                "--entry-point", descriptor.entry_point, "--code-sha256", descriptor.code_sha256]
        raw = _bounded_process(argv, data, env, home, timeout, limit)
        response = decode_json(raw, max_bytes=limit)
        if response.get("ok") is False:
            error = response.get("error", {})
            raise ControlError(error.get("code", "PLUGIN_INCOMPATIBLE"),
                               error.get("message", "installed plugin failed"))
        if set(response) != {"ok", "result"} or response["ok"] is not True or not isinstance(response["result"], dict):
            raise ControlError("PLUGIN_INCOMPATIBLE", "invalid plugin response envelope")
        return response["result"]


class EngineProxy:
    def __init__(self, host: PluginHost, engine_id: str):
        self.host, self.engine_id = host, engine_id

    def info(self):
        return from_wire(self.host.call(self.engine_id, "info", {}), PluginInfo)

    def probe(self, site_runtime):
        return from_wire(self.host.call(self.engine_id, "probe", {"site_runtime": to_wire(site_runtime)}), ProbeReport)

    def validate(self, task, context):
        safe = replace(context, site=_private_site(context.site, self.engine_id))
        return from_wire(self.host.call(self.engine_id, "validate",
                         {"task": to_wire(task), "context": to_wire(safe)}), ValidationReport)

    def prepare(self, task, context):
        safe = replace(context, site=_private_site(context.site, self.engine_id))
        return from_wire(self.host.call(self.engine_id, "prepare",
                         {"task": to_wire(task), "context": to_wire(safe)}), ExecutionPlan)

    def parse(self, snapshot, contract):
        return from_wire(self.host.call(self.engine_id, "parse",
                         {"snapshot": to_wire(snapshot), "contract": contract}), ParseReport)
