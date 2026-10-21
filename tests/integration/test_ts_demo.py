import shutil
import sys

import pytest

from tests.plugins.conftest import plugin_environment
from tests.support.native import HELPERS

TSP = shutil.which("tsp")
pytestmark = [pytest.mark.task_spooler, pytest.mark.linux,
              pytest.mark.skipif(sys.platform != "linux" or not TSP, reason="private Linux Task Spooler binary required")]
TS_HELPERS = HELPERS + r"""
import re
def make_ts(name,script):
 options={"executable":TSP_BINARY,"socket_path":str(site.root/name/"tsp.sock"),
  "max_cpus":2,"max_memory_mib":512}
 return make_native(name,script,executor=ExecutorConfig("task-spooler","example-ts",options))
def stop_queue(service):
 try:
  if service.broker.executor.socket_path.exists():
   service.broker.executor.cli.run(["-K"],service.broker.executor.socket_path)
 finally: service.broker.store.close()
def queue_rows(service):
 data=service.broker.executor.cli.run(["-l"],service.broker.executor.socket_path).decode()
 return re.findall(r"(?m)^([0-9]+)\s",data)
"""


def test_ts_native_demo_and_repeat_submit(plugin_environment):
    plugin_environment("TSP_BINARY=" + repr(TSP) + "\n" + TS_HELPERS + '''
service,request,context=make_ts("ts-demo","import time;time.sleep(.2);print('ts-native')")
try:
 one=service.broker.submit(request,context)
 two=service.broker.submit(request,context)
 assert one.run_id==two.run_id
 observed=terminal(service.broker.executor,one.handle)
 assert observed.execution_state=="COMPLETED",observed
 assert len(queue_rows(service))==1
 assert "ts-native" in (Path(one.handle.run_root)/"stdout.log").read_text()
finally: stop_queue(service)
''')


def test_real_ts_response_loss_reconciles_without_new_compute(plugin_environment):
    plugin_environment("TSP_BINARY=" + repr(TSP) + "\n" + TS_HELPERS + '''
from chat_hpc_control.contracts.errors import ControlError
service,request,context=make_ts("ts-response-loss","import time;time.sleep(.5);print('once')")
executor=service.broker.executor
original=executor.cli.run
def lost(argv,socket_path):
 data=original(argv,socket_path)
 if argv[0]=="-N": raise ConnectionError("simulated missing enqueue reply")
 return data
try:
 executor.cli.run=lost
 try: service.broker.submit(request,context)
 except ControlError as e: assert e.code=="SUBMISSION_UNKNOWN"
 else: raise AssertionError("lost response was treated as certain")
 executor.cli.run=original
 assert service.broker.submit(request,context).execution_state=="SUBMISSION_UNKNOWN"
 reservation=service.broker.store.list_unresolved()[0]
 recovery=executor.reconcile(reservation)
 assert recovery.outcome=="SUBMITTED",recovery
 service.broker.store.record_receipt(reservation,recovery.receipt)
 receipt=service.broker.submit(request,context)
 assert terminal(executor,receipt.handle).execution_state=="COMPLETED"
 assert len(queue_rows(service))==1
finally:
 executor.cli.run=original
 stop_queue(service)
''')


def test_queue_number_reuse_preserves_old_terminal_identity(plugin_environment):
    plugin_environment("TSP_BINARY=" + repr(TSP) + "\n" + TS_HELPERS + '''
from dataclasses import replace
service,request,context=make_ts("ts-reuse","import time;time.sleep(.1);print('done')")
executor=service.broker.executor
try:
 one=service.broker.submit(request,context)
 assert terminal(executor,one.handle).execution_state=="COMPLETED"
 executor.cli.run(["-K"],executor.socket_path)
 assert executor.query(one.handle).execution_state=="COMPLETED"
 executor.instance_path.unlink()
 if executor.socket_path.exists(): executor.socket_path.unlink()
 second=replace(request,idempotency_key="intent-2",rerun_of=one.run_id)
 two=service.broker.submit(second,context)
 assert two.handle.job_id==one.handle.job_id
 assert two.run_id!=one.run_id
 assert executor.query(one.handle).execution_state=="COMPLETED"
 borrowed=replace(one.handle,run_root=two.handle.run_root)
 assert executor.query(borrowed).execution_state=="UNKNOWN"
 assert terminal(executor,two.handle).execution_state=="COMPLETED"
finally: stop_queue(service)
''')


def test_unmanaged_existing_socket_is_not_adopted(plugin_environment):
    plugin_environment("TSP_BINARY=" + repr(TSP) + "\n" + TS_HELPERS + '''
import socket
from chat_hpc_control.contracts.errors import ControlError
service,request,context=make_ts("ts-unmanaged","print('unused')")
executor=service.broker.executor
fake=socket.socket(socket.AF_UNIX);fake.bind(str(executor.socket_path));fake.listen(1)
inode=executor.socket_path.stat().st_ino
try:
 try: executor.ensure_queue()
 except ControlError as e: assert e.code=="JOB_IDENTITY_UNVERIFIED"
 else: raise AssertionError("unmanaged socket adopted")
 assert executor.socket_path.stat().st_ino==inode
 assert not executor.instance_path.exists()
finally:
 fake.close();executor.socket_path.unlink();service.broker.store.close()
''')


def test_read_after_queue_loss_cannot_start_new_server(plugin_environment):
    plugin_environment("TSP_BINARY=" + repr(TSP) + "\n" + TS_HELPERS + '''
service,request,context=make_ts("ts-read-no-create","import time;time.sleep(2)")
executor=service.broker.executor
try:
 receipt=service.broker.submit(request,context)
 executor.cli.run(["-K"],executor.socket_path)
 executor.instance_path.unlink()
 if executor.socket_path.exists(): executor.socket_path.unlink()
 observed=executor.query(receipt.handle)
 assert observed.execution_state=="UNKNOWN",observed
 assert not executor.instance_path.exists(),"read created a replacement queue"
 assert not executor.socket_path.exists(),"read restarted a queue"
finally: stop_queue(service)
''')
