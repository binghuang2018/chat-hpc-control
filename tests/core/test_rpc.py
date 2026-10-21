import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from chat_hpc_control.contracts.tools import ToolCall
from tests.core.test_config import config_text

pytestmark = [pytest.mark.linux, pytest.mark.skipif(sys.platform != "linux", reason="Linux peer credentials required")]


@pytest.fixture
def daemon(tmp_path):
    cfg = tmp_path / "site.toml"
    text = config_text(tmp_path / "site").replace("pyscf", "demo").replace('"1000"', f'"{os.getuid()}"')
    text = text.replace('scopes = ["tasks:submit", "tasks:read"]',
                        'scopes = ["capabilities:read", "tasks:validate", "tasks:submit", "tasks:read", "results:read"]')
    cfg.write_text(text)
    log = (tmp_path / "server.log").open("w+")
    proc = subprocess.Popen([sys.executable, "-m", "tests.support.rpc_server", str(cfg)],
                            stdout=log, stderr=log)
    sock = tmp_path / "site" / "broker.sock"
    end = time.monotonic() + 40
    try:
        while time.monotonic() < end:
            if sock.exists() or proc.poll() is not None:
                break
            time.sleep(.05)
        log.seek(0)
        assert proc.poll() is None and sock.exists(), log.read()
        yield sock, cfg, proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log.close()


def test_rpc_roundtrip_and_peer_identity(daemon):
    from chat_hpc_control.core.rpc import rpc_call
    sock, cfg, proc = daemon
    answer = rpc_call(sock, ToolCall("list_capabilities", {"site_id": "example-site"}))
    assert answer.ok and answer.data["engines"][0]["engine_id"] == "demo"
    assert oct(sock.stat().st_mode & 0o777) == "0o600"


def test_socket_peer_cannot_claim_gateway(daemon):
    import socket
    from chat_hpc_control.contracts.codec import decode_json
    sock, cfg, proc = daemon
    message = {"call": {"name": "list_capabilities", "arguments": {"site_id": "example-site"}},
               "context": {"principal": "admin", "site_id": "example-site", "scopes": ["tasks:submit"], "transport": "mcp"}}
    with socket.socket(socket.AF_UNIX) as client:
        client.connect(str(sock))
        client.sendall(json.dumps(message).encode() + b"\n")
        raw = client.makefile("rb").readline()
    answer = decode_json(raw)
    assert not answer["ok"] and answer["error"]["code"] == "AUTH_DENIED"


def test_second_daemon_cannot_own_site(daemon):
    sock, cfg, proc = daemon
    second = subprocess.run([sys.executable, "-m", "tests.support.rpc_server", str(cfg)],
                            capture_output=True, text=True, timeout=20)
    assert second.returncode == 2
    assert "BROKER_ALREADY_RUNNING" in second.stderr
