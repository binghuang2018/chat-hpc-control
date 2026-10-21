"""Explicit private TOML configuration; loading does not deploy anything."""

import os
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit

from ..contracts.codec import validate_schema
from ..contracts.config import ExecutorConfig, RuntimeConfig, SiteConfig
from ..contracts.errors import ControlError

SCOPES = {"capabilities:read", "tasks:validate", "tasks:submit", "tasks:read", "results:read"}


def _invalid(message: str):
    raise ControlError("SCHEMA_INVALID", message)


def load_site(path: Path) -> SiteConfig:
    try:
        obj = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ControlError("SCHEMA_INVALID", "site TOML is unavailable or malformed") from exc
    validate_schema("site-v1", obj)
    root = Path(obj["root"])
    if not root.is_absolute() or len(root.parts) < 3 or root.is_symlink() or (root.exists() and not root.is_dir()):
        _invalid("site root must be an explicit dedicated absolute directory")
    required_limits = {"max_input_files", "max_input_bytes", "max_output_files", "max_output_bytes"}
    if not required_limits <= obj["limits"].keys():
        _invalid("explicit input/output limits are required")
    principals = obj["principals"]
    for principal, policy in principals.items():
        if (not principal or not isinstance(policy, dict)
                or set(policy) - {"scopes", "engines", "repositories", "read_all"}
                or not {"scopes", "engines", "repositories"} <= policy.keys()
                or not isinstance(policy["scopes"], list)
                or any(s not in SCOPES for s in policy["scopes"])
                or not isinstance(policy["engines"], list)
                or not all(isinstance(e, str) for e in policy["engines"])
                or not isinstance(policy["repositories"], list)
                or not all(isinstance(r, str) for r in policy["repositories"])
                or type(policy.get("read_all", False)) is not bool):
            _invalid("invalid principal policy")
    runtimes = {}
    for engine, runtime in obj["engines"].items():
        if (not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", engine)
                or not isinstance(runtime, dict)
                or set(runtime) - {"executable", "version_args", "environment", "mpi_argv", "options"}
                or "executable" not in runtime):
            _invalid("invalid engine runtime")
        executable = Path(runtime["executable"])
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            _invalid("configured executable must exist at an absolute path")
        environment = runtime.get("environment", {})
        if not isinstance(environment, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                       for k, v in environment.items()):
            _invalid("runtime environment must be a string mapping")
        if any(re.search(r"TOKEN|SECRET|PASSWORD|PRIVATE_KEY|API_?KEY|ACCESS_KEY", k, re.I) for k in environment):
            _invalid("control-plane credentials are not runtime variables")
        for key in ("version_args", "mpi_argv"):
            if key in runtime and (not isinstance(runtime[key], list)
                                    or not all(isinstance(a, str) and "\x00" not in a for a in runtime[key])):
                _invalid("runtime argv must be a string list")
        runtimes[engine] = RuntimeConfig(str(executable), tuple(runtime.get("version_args", ["--version"])),
                                         environment, tuple(runtime.get("mpi_argv", [])), runtime.get("options", {}))
    local = {}
    for uid, principal in obj["local_principals"].items():
        if not uid.isdecimal() or principal not in principals:
            _invalid("local UID mapping references an unknown principal")
        local[int(uid)] = principal
    for repository, mirror in obj["repositories"].items():
        parsed = urlsplit(repository)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or not Path(mirror).is_absolute()):
            _invalid("repository mappings require explicit HTTPS identity and absolute mirror")
    config = ExecutorConfig(**obj["executor"])
    for key in ("max_cpus", "max_memory_mib"):
        if type(config.options.get(key)) is not int or config.options[key] <= 0:
            _invalid("executor requires positive resource capacities")
    return SiteConfig(obj["site_id"], root, principals, runtimes, config, obj["repositories"],
                      obj["limits"], obj["policy_revision"], tuple(obj["gateway_uids"]), local, obj["settings"])
