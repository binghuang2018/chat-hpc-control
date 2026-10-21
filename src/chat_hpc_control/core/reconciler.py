"""The single broker writer observes and collects independently of API reads."""

from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.results import ParseReport
from ..contracts.auth import CallContext
from ..executors.loader import load_executor
from ..plugins.host import EngineProxy,PluginHost
from ..plugins.discovery import discover_enabled
from ..results.snapshot import snapshot_outputs
from ..results.collections import create_collection
from ..results.reader import CollectionReader
from .store import TERMINAL


def reconcile_once(store,site):
    executor=load_executor(site);reader=CollectionReader(store,site);updated=[]
    descriptors=discover_enabled(site)
    for reservation in store.list_unresolved():
        try:
            recovery=executor.reconcile(reservation)
            if recovery.outcome=='SUBMITTED' and recovery.receipt:
                store.record_receipt(reservation,recovery.receipt);updated.append(reservation.run_id)
        except (OSError,ValueError):pass
    for row in store.list_runs():
        reservation=store.find_key(row['site_id'],row['owner'],row['idempotency_key'])
        receipt=store.get_receipt(reservation)
        if receipt.handle is None:continue
        try:
            if row['execution_state'] not in TERMINAL:
                observation=executor.query(receipt.handle)
                if observation.execution_state!=row['execution_state'] or observation.identity_verified:
                    store.update_state(reservation.reservation_id,observation.execution_state,
                        {**row['evidence'],'native':observation.evidence,'identity_verified':observation.identity_verified})
                    updated.append(row['run_id'])
                row=store.get_run(row['run_id'])
            if row['execution_state'] not in TERMINAL:continue
            task=row['request']['task']
            descriptor=descriptors.get(task['engine_id'])
            code_sha=descriptor.code_sha256 if descriptor else None
            if (row['evidence'].get('collection_state')=='COLLECTED'
                    and (code_sha is None or row['evidence'].get('collection_plugin_sha256')==code_sha)):
                manifest=reader.get_manifest(row['run_id'],row['evidence']['collection_id'],
                    CallContext(
                        row['owner'],site.site_id,frozenset({'results:read'})))
                states={r['state'] for r in manifest['publication_receipts']}
                publication='PUBLISHED' if 'PUBLISHED' in states else 'PUBLISH_UNKNOWN' if states else 'NOT_REQUESTED'
                if row['evidence'].get('publication_state','NOT_REQUESTED')!=publication:
                    store.update_state(reservation.reservation_id,row['execution_state'],{**row['evidence'],'publication_state':publication})
                    updated.append(row['run_id'])
                continue
            if descriptor is None:
                raise ControlError('CAPABILITY_UNSUPPORTED','historical engine is disabled; existing collections remain readable')
            snapshot=snapshot_outputs(receipt.handle,site)
            task=row['request']['task']
            report=EngineProxy(PluginHost(site),task['engine_id']).parse(snapshot,task['expected_results'])
            ref=create_collection(row['run_id'],snapshot,report)
            reader.index(ref)
            store.update_state(reservation.reservation_id,row['execution_state'],{**row['evidence'],
                'collection_state':'COLLECTED','collection_id':ref.collection_id,'collection_plugin_sha256':code_sha})
            updated.append(row['run_id'])
        except (OSError,ValueError) as exc:
            evidence={**row['evidence'],'collection_state':'UNVERIFIED','collection_error':
                      exc.code if isinstance(exc,ControlError) else 'RESULT_UNVERIFIED'}
            store.update_state(reservation.reservation_id,row['execution_state'],evidence)
    return sorted(set(updated))
