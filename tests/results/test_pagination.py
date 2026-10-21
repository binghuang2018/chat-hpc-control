from dataclasses import replace
import importlib
import json
import pytest
from tests.core.test_idempotency import setup_broker
from chat_hpc_control.contracts.execution import SubmissionRequest


def test_pinned_pages_and_authorization(setup_broker):
    try:
        module=importlib.import_module('chat_hpc_control.results.reader')
        collections=importlib.import_module('chat_hpc_control.results.collections')
    except ModuleNotFoundError:pytest.fail('collection reader missing')
    broker,task,context,*_=setup_broker
    context=replace(context,scopes=context.scopes|{"results:read"})
    try:
        validated=broker.validate(task,context)
        receipt=broker.submit(SubmissionRequest(context.site_id,task,validated.manifest_sha256,'page-intent'),context)
        run=broker.site.root/'runs'/receipt.run_id
        # Explicit synthetic collection fixture, not native execution evidence.
        from chat_hpc_control.contracts.results import OutputSnapshot,ParseReport
        snaproot=broker.site.root/'snapshot-test';snaproot.mkdir()
        (snaproot/'task-manifest.json').write_text(json.dumps({'task':{'expected_results':None}}))
        snap=OutputSnapshot(snaproot,[],'a'*64,{'execution_state':'COMPLETED','integrity':'VERIFIED'})
        report=ParseReport('synthetic',{'version':'1'},[{'record_id':str(i),'energy':float(i)} for i in range(3)])
        ref=collections.create_collection(receipt.run_id,snap,report)
        reader=module.CollectionReader(broker.store,broker.site)
        reader.index(ref)
        first=reader.get_page(receipt.run_id,None,['record_id','energy'],None,1,context)
        newer=collections.create_collection(receipt.run_id,snap,replace(report,parser_identity={'version':'2'},records=[{'record_id':'new'}]))
        reader.index(newer)
        second=reader.get_page(receipt.run_id,None,['record_id','energy'],first.next_cursor,1,context)
        assert second.collection_id==first.collection_id and second.records[0]['record_id']=='1'
        with pytest.raises(Exception):reader.get_page(receipt.run_id,None,['gradient'],first.next_cursor,1,context)
        with pytest.raises(Exception):reader.get_page(receipt.run_id,None,['record_id','energy'],first.next_cursor+'x',1,context)
        with pytest.raises(Exception):reader.get_page(receipt.run_id,None,[],None,1,replace(context,principal='mallory'))
    finally:broker.store.close()


def test_published_receipts_are_pinned_without_changing_numbers(setup_broker):
    from chat_hpc_control.publishers.base import record_publication
    from chat_hpc_control.contracts.results import PublishReceipt
    broker,task,context,*_=setup_broker
    context=replace(context,scopes=context.scopes|{'results:read'})
    # Reuse the standard local synthetic reader test through independent records.
    validated=broker.validate(task,context)
    receipt=broker.submit(SubmissionRequest(context.site_id,task,validated.manifest_sha256,'publication-read'),context)
    from chat_hpc_control.results.collections import create_collection
    from chat_hpc_control.results.reader import CollectionReader
    from chat_hpc_control.contracts.results import OutputSnapshot,ParseReport
    root=broker.site.root/'synthetic-snapshot';root.mkdir()
    (root/'task-manifest.json').write_text(json.dumps({'task':{'expected_results':None}}))
    ref=create_collection(receipt.run_id,OutputSnapshot(root,[],'a'*64,{'execution_state':'COMPLETED'}),
                          ParseReport('synthetic',{'version':'1'},[{'record_id':'x','energy':-1.0}]))
    reader=CollectionReader(broker.store,broker.site);reader.index(ref)
    before=(ref.root/'records.json').read_bytes()
    record_publication(broker.site,PublishReceipt(ref.collection_id,'github:example/results:results','PUBLISHED',{'commit':'a'*40}))
    manifest=reader.get_manifest(receipt.run_id,ref.collection_id,context)
    assert manifest['publication_receipts'][0]['identity']['commit']=='a'*40
    assert before==(ref.root/'records.json').read_bytes()
