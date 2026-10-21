import sys

import pytest

from tests.plugins.conftest import plugin_environment
from tests.support.native import HELPERS

pytestmark = [pytest.mark.linux, pytest.mark.skipif(sys.platform != "linux", reason="Linux detached execution required")]


def test_broker_restart_retains_native_run(plugin_environment):
    plugin_environment(HELPERS + '''
service,request,context=make_native("restart-case","import time;time.sleep(1);print('survived')")
receipt=service.broker.submit(request,context)
service.broker.store.close()
replacement=build_service(service.broker.site)
try:
 old=replacement.broker.submit(request,context)
 assert old.run_id==receipt.run_id and old.handle.job_id==receipt.handle.job_id
 observed=terminal(replacement.broker.executor,old.handle)
 assert observed.execution_state=="COMPLETED",observed
 assert len(replacement.broker.store.list_runs())==1
finally:
 replacement.broker.store.close()
''')


def test_exiting_client_process_does_not_kill_worker(plugin_environment):
    plugin_environment(HELPERS + '''
import subprocess
service,request,context=make_native("client-disconnect","import time;time.sleep(1);print('detached')")
receipt=service.broker.submit(request,context)
saved=site.root/"detached-handle.json"
from dataclasses import asdict
saved.write_text(json.dumps(asdict(receipt.handle)))
service.broker.store.close()
''')
    plugin_environment('''
import json,time
from chat_hpc_control.contracts.execution import RunHandle
from chat_hpc_control.executors.local import LocalExecutor
from dataclasses import replace
handle=RunHandle(**json.loads((site.root/"detached-handle.json").read_text()))
own=replace(site,root=Path(handle.run_root).parents[1],
 executor=ExecutorConfig("local","example-local",{"max_cpus":2,"max_memory_mib":512}))
executor=LocalExecutor(own)
end=time.monotonic()+30
while time.monotonic()<end:
 result=executor.query(handle)
 if result.execution_state=="COMPLETED": break
 assert result.execution_state not in {"UNKNOWN","FAILED"},result
 time.sleep(.05)
else: raise AssertionError("detached worker never completed")
assert "detached" in (Path(handle.run_root)/"stdout.log").read_text()
''')
