def test_worker_environment_has_no_parent_credentials(plugin_environment):
    plugin_environment('''
proxy=EngineProxy(PluginHost(site),"inspect")
assert proxy.info().engine_id=="inspect"
probe=proxy.probe(site.engines["inspect"])
names=probe.identity["environment_names"]
assert not any(k in names for k in ("OPENAI_API_KEY","GITHUB_TOKEN","ANTHROPIC_API_KEY"))
assert "fixture_qc" not in sys.modules
''', extra_env={"OPENAI_API_KEY": "synthetic-test-not-a-key", "GITHUB_TOKEN": "synthetic",
               "ANTHROPIC_API_KEY": "synthetic"})


def test_method_allowlist_and_response_bound(plugin_environment):
    plugin_environment('''
from dataclasses import replace
from chat_hpc_control.contracts.errors import ControlError
try: PluginHost(site).call("demo","__import__",{})
except ControlError as e: assert e.code=="SCHEMA_INVALID"
else: raise AssertionError("arbitrary method accepted")
small=replace(site,settings={**site.settings,"plugin_rpc_max_bytes":128})
try: EngineProxy(PluginHost(small),"demo").info()
except ControlError as e: assert e.code=="PLUGIN_INCOMPATIBLE"
else: raise AssertionError("over-limit message accepted")
''')


def test_third_party_distribution_and_core_identity(plugin_environment):
    plugin_environment('''
import hashlib
from importlib.resources import files
before=hashlib.sha256(files("chat_hpc_control").joinpath("__init__.py").read_bytes()).hexdigest()
info=EngineProxy(PluginHost(site),"demo").info()
assert info.engine_id=="demo"
assert info.profiles==("demo-json-v1","raw-only")
assert len(info.code_sha256)==64 and info.code_sha256!="0"*64
after=hashlib.sha256(files("chat_hpc_control").joinpath("__init__.py").read_bytes()).hexdigest()
assert before==after
''')


def test_typed_bytes_and_minimal_context(plugin_environment):
    plugin_environment('''
import json, hashlib
from dataclasses import replace
from chat_hpc_control.contracts.plugins import ValidationContext
from chat_hpc_control.contracts.task import TaskSpec, ResolvedTask, ResourceRequest
task=TaskSpec("inspect-1","inspect",{"looks_typed":{"$type":"Path","value":"/etc/passwd"}},
 {"kind":"bundle","bundle_id":"test"},"job.py",ResourceRequest(1,64,None),None)
full=replace(site,principals={"private-user":{"scopes":["tasks:submit"]}},
 settings={**site.settings,"bearer_tokens":["synthetic-secret-reference"]})
resolved=ResolvedTask(task,{"job.py":b"raw script bytes"},{"kind":"bundle","bundle_id":"test"})
result=EngineProxy(PluginHost(site),"inspect").validate(resolved,ValidationContext(full))
observed=json.loads(result.issues[0])
assert observed["files"]=={"job.py":hashlib.sha256(b"raw script bytes").hexdigest()}
assert observed["options_type"]=="dict"
assert observed["principals"]==[]
assert observed["settings_keys"]==[]
assert observed["site_engine_ids"]==["inspect"]
''')


def test_invalid_control_timeout_is_rejected_before_launch(plugin_environment):
    plugin_environment('''
from dataclasses import replace
from chat_hpc_control.contracts.errors import ControlError
invalid=replace(site,settings={**site.settings,"plugin_control_timeout_seconds":"invalid"})
try: EngineProxy(PluginHost(invalid),"demo").info()
except ControlError as e: assert e.code=="SCHEMA_INVALID"
else: raise AssertionError("invalid control timeout accepted")
''')


def test_running_child_timeout_and_stderr_are_bounded(plugin_environment):
    plugin_environment('''
import time
from dataclasses import replace
from chat_hpc_control.contracts.errors import ControlError
cases=[
 ({"plugin_control_timeout_seconds":0.05},{"sleep_seconds":1}),
 ({"plugin_rpc_max_bytes":4096},{"noise_bytes":32768}),
]
for settings,options in cases:
 bounded=replace(site,settings={**site.settings,**settings})
 runtime=replace(site.engines["inspect"],options=options)
 start=time.monotonic()
 try: EngineProxy(PluginHost(bounded),"inspect").probe(runtime)
 except ControlError as e: assert e.code=="PLUGIN_INCOMPATIBLE"
 else: raise AssertionError("unbounded worker accepted")
 assert time.monotonic()-start < 5
''')
