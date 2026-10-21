import json
from pathlib import Path
import subprocess
import sys


def cli(*args):
    return subprocess.run([sys.executable, "-m", "chat_hpc_control.cli", *args],
                          capture_output=True, text=True)


def test_help_has_no_optional_dependency_requirement():
    result = cli("--help")
    assert result.returncode == 0, result.stderr
    assert "validate" in result.stdout and "submit" in result.stdout


def test_cli_json_schema_only(sample_task, tmp_path):
    path = tmp_path / "task.json"
    path.write_text(json.dumps(sample_task))
    result = cli("validate", "--task", str(path), "--schema-only")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["data"]["validation_level"] == "SCHEMA_ONLY"
    assert data["data"]["valid"] is True
    assert "manifest_sha256" not in data["data"]


def test_cli_invalid_json_is_exit_two(tmp_path):
    path = tmp_path / "task.json"
    path.write_text('{"resources":NaN}')
    result = cli("validate", "--task", str(path), "--schema-only")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "SCHEMA_INVALID"


def test_cli_communication_error_is_exit_three(tmp_path):
    from tests.core.test_config import config_text
    path = tmp_path / "site.toml"
    path.write_text(config_text(tmp_path / "runtime"))
    result = cli("--site", str(path), "status", "absent-run")
    assert result.returncode == 3
    assert json.loads(result.stdout)["error"]["code"] == "BROKER_UNAVAILABLE"
