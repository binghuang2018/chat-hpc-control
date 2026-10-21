import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture(scope="session")
def plugin_environment(tmp_path_factory):
    assert importlib.util.find_spec("chat_hpc_control.plugins") is not None, "isolated plugin host is missing"
    root = Path(__file__).resolve().parents[2]
    demo = root / "examples/plugins/demo-engine"
    assert (demo / "pyproject.toml").is_file(), "third-party demo distribution is missing"
    temp = tmp_path_factory.mktemp("plugin-env")
    wheels = temp / "wheels"
    wheels.mkdir()
    for project in (root, demo):
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheels), str(project)],
                       check=True, capture_output=True, text=True)
    test_pkg = temp / "fixture-package"
    test_pkg.mkdir()
    (test_pkg / "pyproject.toml").write_text('''
[build-system]
requires = ["hatchling>=1.32.4,<2"]
build-backend = "hatchling.build"
[project]
name = "chat-hpc-test-engine"
version = "0.1.0"
[project.entry-points."chat_hpc_control.engines"]
inspect = "fixture_qc:create_inspector"
incompatible = "fixture_qc:create_incompatible"
[tool.hatch.build.targets.wheel]
packages = ["fixture_qc.py"]
''')
    (test_pkg / "fixture_qc.py").write_text('''
import os, json, hashlib, time
from chat_hpc_control.contracts.plugins import PluginInfo, ProbeReport, ValidationReport
class Inspector:
    def __init__(self, engine_id="inspect", api="1.0"):
        self.engine_id, self.api = engine_id, api
    def info(self):
        return PluginInfo(self.engine_id, "chat-hpc-test-engine", "0.1.0", "a"*64, api_version=self.api)
    def probe(self, runtime):
        time.sleep(runtime.options.get("sleep_seconds", 0))
        if runtime.options.get("noise_bytes"):
            print("x"*runtime.options["noise_bytes"])
        return ProbeReport(True, "synthetic", {"environment_names": sorted(os.environ)})
    def validate(self, task, context):
        observation = {"site_engine_ids":sorted(context.site.engines),
          "principals":list(context.site.principals), "settings_keys":list(context.site.settings),
          "files":{k:hashlib.sha256(v).hexdigest() for k,v in task.files.items()},
          "options_type":type(task.task.engine_options.get("looks_typed")).__name__}
        return ValidationReport(True,task.task,issues=(json.dumps(observation),))
def create_inspector(): return Inspector()
def create_incompatible(): return Inspector("incompatible", "2.0")
''')
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheels), str(test_pkg)],
                   check=True, capture_output=True, text=True)
    env = temp / "env"
    subprocess.run(["uv", "venv", "--python", sys.executable, str(env)], check=True, capture_output=True)
    subprocess.run(["uv", "pip", "install", "--python", str(env / "bin/python"),
                    *map(str, wheels.glob("*.whl"))], check=True, capture_output=True)
    def run(script, *, extra_env=None):
        prelude = '''
import sys
from pathlib import Path
from chat_hpc_control.contracts.config import SiteConfig, RuntimeConfig, ExecutorConfig
from chat_hpc_control.plugins.host import PluginHost, EngineProxy
from chat_hpc_control.plugins.discovery import discover_enabled
site = SiteConfig("example-site", Path(RUNTIME_ROOT), {}, {
 "demo": RuntimeConfig(sys.executable), "inspect": RuntimeConfig(sys.executable),
 "incompatible": RuntimeConfig(sys.executable)}, ExecutorConfig("local","example"),
 settings={"plugin_allowlist": {"demo":"chat-hpc-demo-engine",
 "inspect":"chat-hpc-test-engine", "incompatible":"chat-hpc-test-engine"}})
'''
        prelude = "RUNTIME_ROOT=" + repr(str(temp / "runtime")) + "\n" + prelude
        client_home = temp / "client-home"
        client_home.mkdir(mode=0o700, exist_ok=True)
        actual_env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(client_home), "LANG": "C.UTF-8"}
        if extra_env:
            actual_env.update(extra_env)
        result = subprocess.run([str(env / "bin/python"), "-c", prelude + "\n" + script],
                                cwd=temp, env=actual_env, text=True, capture_output=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    return run
