def test_metadata_without_parent_import(plugin_environment):
    plugin_environment('''
found=discover_enabled(site)
assert set(found)=={"demo","inspect","incompatible"}
assert "chat_hpc_demo.plugin" not in sys.modules
assert "fixture_qc" not in sys.modules
assert found["demo"].distribution=="chat-hpc-demo-engine"
''')


def test_disabled_plugin_and_distribution_allowlist(plugin_environment):
    plugin_environment('''
from dataclasses import replace
from chat_hpc_control.contracts.errors import ControlError
limited=replace(site,engines={"demo":site.engines["demo"]},settings={"plugin_allowlist":{}})
try:
 discover_enabled(limited)
except ControlError as e:
 assert e.code=="PLUGIN_INCOMPATIBLE"
else:
 raise AssertionError("unapproved distribution was accepted")
try:
 PluginHost(site).call("not-enabled","info",{})
except ControlError as e:
 assert e.code=="CAPABILITY_UNSUPPORTED"
else:
 raise AssertionError("disabled plugin was loaded")
''')


def test_api_major_is_checked_in_worker(plugin_environment):
    plugin_environment('''
from chat_hpc_control.contracts.errors import ControlError
try:
 EngineProxy(PluginHost(site),"incompatible").info()
except ControlError as e:
 assert e.code=="PLUGIN_INCOMPATIBLE"
else:
 raise AssertionError("API 2 plugin was accepted")
''')


def test_duplicate_id_is_not_silently_selected(plugin_environment):
    plugin_environment('''
import importlib.metadata as md
from chat_hpc_control.contracts.errors import ControlError
from unittest.mock import patch
entries=md.entry_points(group="chat_hpc_control.engines")
demo=next(ep for ep in entries if ep.name=="demo")
with patch("chat_hpc_control.plugins.discovery.installed_entries",return_value=[demo,demo]):
 try: discover_enabled(site)
 except ControlError as e: assert e.code=="PLUGIN_INCOMPATIBLE"
 else: raise AssertionError("duplicate engine ID accepted")
''')
