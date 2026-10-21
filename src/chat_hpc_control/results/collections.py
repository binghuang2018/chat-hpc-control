"""Content-addressed immutable result files; mutable pointers live elsewhere."""

import hashlib
import json
from pathlib import Path
from ..contracts.codec import check_json_tree,decode_json
from ..contracts.results import CollectionRef
from ..worker.receipt import write_once
from .completeness import assess


def result_bytes(value):
    check_json_tree(value,allow_float=True)
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()


def create_collection(run_id,snapshot,report):
    contract=decode_json((snapshot.root/'task-manifest.json').read_bytes())['task']['expected_results']
    assessment=assess(snapshot,report,contract)
    # Invalid numerical records cannot be encoded as JSON: retain their issue and
    # original raw evidence; never normalize a NaN into a scientific number.
    records=[]
    for record in report.records:
        try:result_bytes(record)
        except ValueError:continue
        records.append(record)
    documents={
        'summary.json':{k:v for k,v in assessment.items() if k!='issues'},
        'completeness.json':assessment,
        'records.json':{'records':records},
        'provenance.json':{'schema':'chat-hpc-control/collection-provenance/v1','run_id':run_id,
             'manifest_sha256':snapshot.manifest_sha256,'terminal':snapshot.terminal,
             'parser':report.parser_identity,'profile':report.profile,'contract':contract,
             'assessment':{'version':'1','code_sha256':hashlib.sha256(Path(__file__).with_name('completeness.py').read_bytes()).hexdigest()},
             'snapshot_identity':hashlib.sha256(result_bytes(snapshot.files)).hexdigest(),
             'snapshot_sha256':hashlib.sha256(result_bytes({'files':snapshot.files,'terminal':snapshot.terminal,
                 'manifest_sha256':snapshot.manifest_sha256})).hexdigest()},
        'raw-manifest.json':{'files':snapshot.files}}
    payload={name:result_bytes(data) for name,data in documents.items()}
    inventory=[{'path':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in sorted(payload.items())]
    identity={'schema':'chat-hpc-control/collection/v1','run_id':run_id,'files':inventory}
    digest=hashlib.sha256(result_bytes(identity)).hexdigest()
    target=snapshot.root.parent/'collections'/run_id/digest
    for name,raw in payload.items():
        write_once(target/name,raw);(target/name).chmod(0o400)
    write_once(target/'collection.json',result_bytes(identity))
    return CollectionRef(run_id,digest,target)


def read_collection(ref):
    from ..sources.bundle import read_verified
    raw=(ref.root/'collection.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref.collection_id:raise ValueError('collection identity changed')
    manifest=decode_json(raw)
    if manifest['run_id']!=ref.run_id:raise ValueError('collection run mismatch')
    expected={r['path'] for r in manifest['files']}|{'collection.json'}
    if ref.root.is_symlink() or any(p.is_symlink() for p in ref.root.rglob('*')):
        raise ValueError('collection contains links')
    if {p.relative_to(ref.root).as_posix() for p in ref.root.rglob('*') if p.is_file()}!=expected:
        raise ValueError('collection file inventory changed')
    data={}
    for record in manifest['files']:
        path=ref.root/record['path']
        content=path.read_bytes()
        if len(content)!=record['size'] or hashlib.sha256(content).hexdigest()!=record['sha256']:
            raise ValueError('collection file hash changed')
        data[record['path']]=decode_json(content)
    return data
