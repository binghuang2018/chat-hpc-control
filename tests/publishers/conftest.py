import hashlib,json
from pathlib import Path
import pytest
from chat_hpc_control.contracts.results import OutputSnapshot,ParseReport
from chat_hpc_control.results.collections import create_collection,result_bytes
from chat_hpc_control.sources.bundle import file_records

@pytest.fixture
def publish_case(tmp_path):
    payload={'stdout.log':b'synthetic output\n','records.json':b'{"records":[]}',
      'task-manifest.json':b'{"task":{"expected_results":null}}'}
    files=file_records(payload);terminal={'execution_state':'COMPLETED','integrity':'VERIFIED'}
    identity={'files':files,'terminal':terminal,'manifest_sha256':'a'*64}
    digest=hashlib.sha256(result_bytes(identity)).hexdigest()
    store=tmp_path/'snapshots';root=store/digest;root.mkdir(parents=True)
    for name,raw in payload.items():(root/name).write_bytes(raw)
    (root/'snapshot.json').write_bytes(result_bytes(identity))
    snap=OutputSnapshot(root,files,'a'*64,terminal)
    ref=create_collection('synthetic-run',snap,ParseReport('raw-only',{'version':'1'},supported=False))
    return ref,store,tmp_path
