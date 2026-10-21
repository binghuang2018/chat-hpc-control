"""Private Linux Unix-socket transport to the site's single writer."""

from dataclasses import asdict
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import sys
import threading
import uuid
import json
import time

from ..contracts.auth import CallContext, PeerIdentity
from ..contracts.codec import MAX_JSON_BYTES, decode_json, encode_response
from ..contracts.errors import ControlError
from ..contracts.tools import ToolCall, ToolResponse
from .auth import context_from_peer


def _error(code, message):
    return ToolResponse(str(uuid.uuid4()), False, error=ControlError(code, message).to_dict())


def serve(site, service) -> None:
    if sys.platform != "linux":
        raise ControlError("CAPABILITY_UNSUPPORTED", "native broker server requires Linux peer credentials")
    path = site.root / "broker.sock"
    if len(os.fsencode(path)) >= 104:
        raise ControlError("RESOURCE_UNSUPPORTED", "choose a shorter private runtime root for Unix socket")
    if path.exists() or path.is_symlink():
        status = path.lstat()
        if not stat.S_ISSOCK(status.st_mode) or status.st_uid != os.geteuid():
            raise ControlError("SCHEMA_INVALID", "refusing to overwrite non-owned socket path")
        path.unlink()
    previous = None
    if threading.current_thread() is threading.main_thread():
        def terminate(_signum, _frame):
            raise KeyboardInterrupt
        previous = signal.signal(signal.SIGTERM, terminate)
    server = socket.socket(socket.AF_UNIX)
    try:
        server.bind(str(path))
        path.chmod(0o600)
        server.listen(16)
        server.settimeout(0.5)
        next_reconcile = 0
        while True:
            if getattr(service, "reconcile", None) and time.monotonic() >= next_reconcile:
                service.reconcile()
                next_reconcile = time.monotonic() + 1
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            with connection:
                connection.settimeout(5)
                try:
                    # Kernel credentials are pid, uid, gid; our value object is uid, gid, pid.
                    raw_credentials = struct.unpack("3i", connection.getsockopt(
                        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
                    peer = PeerIdentity(raw_credentials[1], raw_credentials[2], raw_credentials[0])
                    with connection.makefile("rb") as stream:
                        raw = stream.readline(MAX_JSON_BYTES + 1)
                    if not raw.endswith(b"\n") or len(raw) > MAX_JSON_BYTES:
                        raise ControlError("SCHEMA_INVALID", "RPC frame is incomplete or too large")
                    envelope = decode_json(raw)
                    if set(envelope) - {"call", "context"} or "call" not in envelope:
                        raise ControlError("SCHEMA_INVALID", "unknown RPC envelope fields")
                    context = context_from_peer(peer, envelope, site)
                    call = envelope["call"]
                    if (not isinstance(call, dict) or set(call) - {"name", "arguments", "provider_call_id"}
                            or not {"name", "arguments"} <= call.keys()
                            or not isinstance(call["name"], str) or not isinstance(call["arguments"], dict)):
                        raise ControlError("SCHEMA_INVALID", "invalid RPC tool call")
                    response = service.handle(ToolCall(**call), context)
                except ControlError as exc:
                    response = ToolResponse(str(uuid.uuid4()), False, error=exc.to_dict())
                except (OSError, ValueError):
                    response = _error("SCHEMA_INVALID", "unreadable private RPC frame")
                try:
                    connection.sendall(encode_response(response) + b"\n")
                except OSError:
                    pass
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        if path.exists() and stat.S_ISSOCK(path.lstat().st_mode):
            path.unlink()
        service.broker.store.close()
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def rpc_call(socket_path: Path, call: ToolCall, *, context: CallContext | None = None) -> ToolResponse:
    envelope = {"call": asdict(call)}
    if context is not None:
        identity = {"principal": context.principal, "site_id": context.site_id,
                    "scopes": sorted(context.scopes), "transport": context.transport}
        for key in ("author", "actor"):
            value = getattr(context, key)
            if value is not None:
                identity[key] = value
        envelope["context"] = identity
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(30)
            client.connect(str(socket_path))
            client.sendall(json.dumps(envelope, allow_nan=False, separators=(",", ":")).encode() + b"\n")
            with client.makefile("rb") as stream:
                raw = stream.readline(MAX_JSON_BYTES + 1)
        if not raw.endswith(b"\n"):
            raise OSError("incomplete reply")
        return ToolResponse(**decode_json(raw))
    except (OSError, ValueError) as exc:
        raise ControlError("BROKER_UNAVAILABLE", "private broker could not be reached", retryable=True) from exc
