import sys

import pytest

from tests.plugins.conftest import plugin_environment
from tests.support.native import HELPERS

pytestmark = [pytest.mark.linux, pytest.mark.skipif(sys.platform != "linux", reason="Linux execution identity required")]


def test_local_completion_and_environment(plugin_environment):
    plugin_environment(HELPERS + '''
service,request,context=make_native("local-complete",
 "import os,json;print('literal $(touch never-created)');open('observed.json','w').write(json.dumps({'keys':list(os.environ),'affinity':sorted(os.sched_getaffinity(0))}))")
try:
 receipt=service.broker.submit(request,context)
 observed=terminal(service.broker.executor,receipt.handle)
 assert observed.execution_state=="COMPLETED",observed
 assert observed.identity_verified and observed.exit_code==0
 data=json.loads((Path(receipt.handle.run_root)/"work/observed.json").read_text())
 assert not any(k in data["keys"] for k in ["GITHUB_TOKEN","OPENAI_API_KEY","RUNNER_TRACKING_ID"])
 assert len(data["affinity"])==1
 assert not (Path(receipt.handle.run_root)/"work/never-created").exists()
 assert "literal $(touch never-created)" in (Path(receipt.handle.run_root)/"stdout.log").read_text()
finally:
 service.broker.store.close()
''', extra_env={"GITHUB_TOKEN":"synthetic","OPENAI_API_KEY":"synthetic","RUNNER_TRACKING_ID":"synthetic"})


def test_pid_reuse_and_boot_change_are_not_accepted(plugin_environment):
    plugin_environment(HELPERS + '''
from dataclasses import replace
service,request,context=make_native("identity-check","import time;time.sleep(2)")
try:
 receipt=service.broker.submit(request,context)
 handle=receipt.handle
 for identity in [{**handle.identity,"boot_id":"wrong-boot"},
                  {**handle.identity,"start_time":"wrong-start"}]:
  result=service.broker.executor.query(replace(handle,identity=identity))
  assert result.execution_state=="UNKNOWN" and not result.identity_verified
 observed=terminal(service.broker.executor,handle)
 assert observed.execution_state=="COMPLETED",observed
 assert service.broker.executor.query(handle).execution_state=="COMPLETED"
finally:
 service.broker.store.close()
''')


def test_walltime_none_survives_control_wait_and_finite_limit_terminates(plugin_environment):
    plugin_environment(HELPERS + '''
for name,walltime,expected in [("no-limit",None,"COMPLETED"),("finite-limit",1,"FAILED")]:
 service,request,context=make_native(name,"import time;time.sleep(2)",walltime)
 try:
  receipt=service.broker.submit(request,context)
  time.sleep(.05)
  observed=terminal(service.broker.executor,receipt.handle)
  assert observed.execution_state==expected,observed
  if walltime is not None: assert observed.evidence["reason"]=="WALLTIME_EXCEEDED"
 finally:
  service.broker.store.close()
''')


def test_missing_normal_termination_file_is_not_completed(plugin_environment):
    plugin_environment(HELPERS + '''
from dataclasses import replace
service,request,context=make_native("missing-marker","print('ordinary exit')")
original=service.broker.engines["demo"].prepare
def requiring_marker(task,context):
 return replace(original(task,context),program_identity={
  "normal_termination":{"file":"missing.out","marker":"SYNTHETIC DONE"}})
service.broker.engines["demo"].prepare=requiring_marker
try:
 receipt=service.broker.submit(request,context)
 observed=terminal(service.broker.executor,receipt.handle)
 assert observed.execution_state=="FAILED",observed
finally: service.broker.store.close()
''')
