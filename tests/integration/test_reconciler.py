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
