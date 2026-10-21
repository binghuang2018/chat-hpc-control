import importlib,json
import pytest


def parse(snap,contract=None):
    try: return importlib.import_module('chat_hpc_control.engines.parsers.pyscf_json').parse(snap,contract)
    except ModuleNotFoundError: pytest.fail('PySCF parser missing')


def test_script_evidence(snapshot,record):
    result=parse(snapshot({'records.json':json.dumps({'schema':'chat-hpc-control/pyscf-records/v1','records':[record]})}))
    assert result.supported
    assert result.records[0]['evidence_level']=='script-reported'
    assert result.records[0]['energy']==-1.1
    assert result.parser_identity['code_sha256']


@pytest.mark.parametrize('raw',['{"records":','{"records":[],"records":[]}', '{"records":[{"energy":NaN}]}'])
def test_invalid_json_not_success(snapshot,raw):
    result=parse(snapshot({'records.json':raw}))
    assert result.issues and not result.supported
