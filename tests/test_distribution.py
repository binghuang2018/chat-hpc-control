import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_core_import_is_lazy():
    assert (ROOT / "pyproject.toml").is_file(), "installable distribution not implemented"
    code = "import sys, json, chat_hpc_control; print(json.dumps(sorted(sys.modules)))"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    loaded = json.loads(result.stdout)
    assert not any(m.split(".")[0] in {"openai", "anthropic", "google", "mcp", "pyscf"} for m in loaded)


def test_packaged_schema_installs(tmp_path):
    assert (ROOT / "pyproject.toml").is_file(), "installable distribution not implemented"
    out = tmp_path / "dist"
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(out)],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    env = tmp_path / "env"
    subprocess.run(["uv", "venv", "--python", sys.executable, str(env)], check=True, capture_output=True)
    subprocess.run(["uv", "pip", "install", "--python", str(env / "bin/python"), "--no-deps",
                    str(next(out.glob("*.whl")))], check=True, capture_output=True)
    script = 'import json; from importlib.resources import files; print(json.loads(files("chat_hpc_control").joinpath("schemas/task-v1.json").read_text())["title"])'
    result = subprocess.run([str(env / "bin/python"), "-c", script], cwd=tmp_path,
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "chat-hpc-control task v1"
