"""Load only an explicitly approved installed executor entry point."""

from importlib import metadata
from ..contracts.errors import ControlError
from ..plugins.discovery import normalized


def load_executor(site):
    entries = [entry for entry in metadata.entry_points(group="chat_hpc_control.executors")
               if entry.name == site.executor.kind]
    if len(entries) != 1:
        raise ControlError("PLUGIN_INCOMPATIBLE", "executor must have exactly one installed entry point")
    entry = entries[0]
    approved = site.settings.get("executor_allowlist", {}).get(entry.name, "chat-hpc-control")
    if normalized(entry.dist.metadata["Name"]) != normalized(approved):
        raise ControlError("PLUGIN_INCOMPATIBLE", "executor distribution is not approved")
    executor = entry.load()(site)
    if executor.info().api_version.split(".")[0] != "1" or executor.info().executor_id != site.executor.identity:
        raise ControlError("PLUGIN_INCOMPATIBLE", "executor API or identity mismatch")
    return executor
