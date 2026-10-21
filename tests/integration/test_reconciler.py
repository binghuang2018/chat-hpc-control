import sys
import pytest
from tests.plugins.conftest import plugin_environment
from tests.support.native import HELPERS
pytestmark=[pytest.mark.linux,pytest.mark.skipif(sys.platform!='linux',reason='Linux worker required')]


def test_independent_reconciliation_and_result_snapshot(plugin_environment):
    plugin_environment(HELPERS+'''
from chat_hpc_control.core.reconciler import reconcile_once
service,request,context=make_native('collection-demo',"import json;json.dump({'records':[{'record_id':'synthetic','energy':-1.0}]},open('records.json','w'))")
try:
 receipt=service.broker.submit(request,context)
 assert service.reader.get_page(receipt.run_id,None,[],None,10,context).collection_id is None
 assert terminal(service.broker.executor,receipt.handle).execution_state=='COMPLETED'
 updated=reconcile_once(service.broker.store,service.broker.site)
 assert receipt.run_id in updated
 status=service.broker.get_status(receipt.run_id,context)
 assert status.execution_state=='COMPLETED' and status.collection_state=='COLLECTED',status
 page=service.reader.get_page(receipt.run_id,None,['record_id','energy'],None,10,context)
 assert page.collection_id and page.records[0]['energy']==-1.0
 assert not page.summary['data_ready']
 before=page.collection_id
 reconcile_once(service.broker.store,service.broker.site)
 assert service.reader.get_page(receipt.run_id,None,[],None,10,context).collection_id==before
 manifest=service.reader.get_manifest(receipt.run_id,before,context)
 assert any(f['path']=='records.json' for f in manifest['files'])
finally:service.broker.store.close()
''')


def test_snapshot_rejects_output_symlink(plugin_environment):
    plugin_environment(HELPERS+'''
from chat_hpc_control.results.snapshot import snapshot_outputs
from chat_hpc_control.contracts.errors import ControlError
service,request,context=make_native('output-link',"from pathlib import Path;Path('escape').symlink_to('/etc/passwd')")
try:
 receipt=service.broker.submit(request,context)
 assert terminal(service.broker.executor,receipt.handle).execution_state=='COMPLETED'
 try:snapshot_outputs(receipt.handle,service.broker.site)
 except ControlError as e:assert e.code=='RESULT_UNVERIFIED'
 else:raise AssertionError('output symlink accepted')
finally:service.broker.store.close()
''')


def test_snapshot_respects_regular_output_declarations(plugin_environment):
    plugin_environment(HELPERS+'''
from chat_hpc_control.results.snapshot import snapshot_outputs
service,request,context=make_native('output-declaration',"from pathlib import Path;Path('undeclared.txt').write_text('synthetic excluded');Path('records.json').write_text('{\\\"records\\\":[]}')")
try:
 receipt=service.broker.submit(request,context)
 assert terminal(service.broker.executor,receipt.handle).execution_state=='COMPLETED'
 snap=snapshot_outputs(receipt.handle,service.broker.site)
 names={row['path'] for row in snap.files}
 assert 'records.json' in names and 'undeclared.txt' not in names,names
finally:service.broker.store.close()
''')


def test_snapshot_rejects_linked_work_root(plugin_environment):
    plugin_environment(HELPERS+'''
from chat_hpc_control.results.snapshot import snapshot_outputs
from chat_hpc_control.contracts.errors import ControlError
outside=site.root/'synthetic-external';outside.mkdir(parents=True)
(outside/'records.json').write_text('{"records":[]}')
script="import os,shutil;from pathlib import Path;os.chdir('..');shutil.rmtree('work');Path('work').symlink_to("+repr(str(outside))+",target_is_directory=True)"
service,request,context=make_native('linked-work-root',script)
try:
 receipt=service.broker.submit(request,context)
 assert terminal(service.broker.executor,receipt.handle).execution_state=='COMPLETED'
 try:snapshot_outputs(receipt.handle,service.broker.site)
 except ControlError as e:assert e.code=='RESULT_UNVERIFIED'
 else:raise AssertionError('linked work root accepted')
finally:service.broker.store.close()
''')


def test_disabled_engine_preserves_historical_collection(plugin_environment):
    plugin_environment(HELPERS+'''
from dataclasses import replace
from chat_hpc_control.core.reconciler import reconcile_once
service,request,context=make_native('retired-engine',"import json;json.dump({'records':[{'record_id':'synthetic','energy':-1.0}]},open('records.json','w'))")
try:
 receipt=service.broker.submit(request,context)
 assert terminal(service.broker.executor,receipt.handle).execution_state=='COMPLETED'
 reconcile_once(service.broker.store,service.broker.site)
 before=service.reader.get_page(receipt.run_id,None,[],None,10,context).collection_id
 assert before
 retired=replace(service.broker.site,engines={})
 reconcile_once(service.broker.store,retired)
 assert service.reader.get_page(receipt.run_id,None,[],None,10,context).collection_id==before
finally:service.broker.store.close()
''')


def test_queued_runtime_change_refuses_native_launch(plugin_environment):
    plugin_environment(HELPERS+'''
import fcntl
extra=site.root/'queue-runtime';extra.parent.mkdir(parents=True,exist_ok=True);extra.write_text('original')
site=replace(site,engines={**site.engines,'demo':replace(site.engines['demo'],options={'fingerprint_paths':[str(extra)]})})
service,request,context=make_native('queued-runtime',"from pathlib import Path;Path('should-not-run').write_text('executed')")
queue=service.broker.site.root/'local-queue';queue.mkdir()
fd=os.open(queue/'slot-0.lock',os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX)
try:
 receipt=service.broker.submit(request,context)
 time.sleep(1)
 extra.write_text('changed while waiting')
 fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd);fd=None
 observed=terminal(service.broker.executor,receipt.handle)
 assert observed.execution_state=='FAILED',observed
 assert not (Path(receipt.handle.run_root)/'work/should-not-run').exists()
finally:
 if fd is not None:os.close(fd)
 service.broker.store.close()
''')
