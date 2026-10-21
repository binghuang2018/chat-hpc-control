from dataclasses import replace
import importlib
import json
import pytest


def api():
    try:return importlib.import_module('chat_hpc_control.results.collections')
    except ModuleNotFoundError:pytest.fail('immutable collections missing')


def test_immutable_parser_versioned_collection(quantity_case):
    snap,report,contract=quantity_case
    (snap.root/'task-manifest.json').write_text(json.dumps({'task':{'expected_results':contract}}))
    one=api().create_collection('run-test',snap,report)
    two=api().create_collection('run-test',snap,report)
    assert one.collection_id==two.collection_id
    assert (one.root/'summary.json').is_file()
    other=api().create_collection('run-test',snap,replace(report,parser_identity={'version':'2','code_sha256':'b'*64}))
    assert other.collection_id!=one.collection_id
    original=(one.root/'summary.json').read_bytes()
    assert b'NOT_EVALUATED' in original
    (one.root/'summary.json').chmod(0o600)
    (one.root/'summary.json').write_text('{}')
    with pytest.raises(Exception):api().create_collection('run-test',snap,report)
