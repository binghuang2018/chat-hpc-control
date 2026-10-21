import importlib
from pathlib import Path
import sys

import pytest

from chat_hpc_control.contracts.errors import ControlError


def api():
    try:
        return importlib.import_module("chat_hpc_control.core.config")
    except ModuleNotFoundError:
        pytest.fail("explicit site configuration is missing")


def config_text(root):
    return f'''
site_id = "example-site"
root = "{root}"
policy_revision = "1"
gateway_uids = []
[principals.alice]
scopes = ["tasks:submit", "tasks:read"]
engines = ["pyscf"]
repositories = []
[engines.pyscf]
executable = "{sys.executable}"
[executor]
kind = "local"
identity = "example-local"
[executor.options]
max_cpus = 2
max_memory_mib = 1024
[repositories]
[limits]
max_input_files = 10
max_input_bytes = 1024
max_output_files = 10
max_output_bytes = 1024
[local_principals]
"1000" = "alice"
[settings]
'''


def test_valid_site_does_not_create_runtime(tmp_path):
    path = tmp_path / "site.toml"
    root = tmp_path / "runtime"
    path.write_text(config_text(root))
    site = api().load_site(path)
    assert site.root == root
    assert site.local_principals[1000] == "alice"
    assert not root.exists()


@pytest.mark.parametrize("mutation", ["relative", "filesystem_root", "missing_root", "unknown_field", "missing_limits"])
def test_config_paths_and_missing_policy(tmp_path, mutation):
    text = config_text(tmp_path / "runtime")
    if mutation == "relative":
        text = text.replace(str(tmp_path / "runtime"), "relative")
    elif mutation == "filesystem_root":
        text = text.replace(str(tmp_path / "runtime"), "/")
    elif mutation == "missing_root":
        text = "\n".join(line for line in text.splitlines() if not line.startswith("root ="))
    elif mutation == "unknown_field":
        text = 'input_root = "/other-root"\n' + text
    else:
        text = text.replace("max_input_files = 10", "")
    path = tmp_path / "site.toml"
    path.write_text(text)
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        api().load_site(path)


def test_runtime_cannot_carry_model_credentials(tmp_path):
    path = tmp_path / "site.toml"
    path.write_text(config_text(tmp_path / "runtime").replace(
        "[executor]", '[engines.pyscf.environment]\nOPENAI_API_KEY = "synthetic-not-a-key"\n[executor]'))
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        api().load_site(path)


@pytest.mark.parametrize("value", ["0", "-1", "true"])
def test_invalid_queue_concurrency_rejected(tmp_path, value):
    path = tmp_path / "site.toml"
    path.write_text(config_text(tmp_path / "runtime").replace(
        "max_cpus = 2", "max_cpus = 2\nmax_concurrent = " + value))
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        api().load_site(path)
