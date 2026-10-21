"""Copy stable, bounded, regular outputs only after verified native termination."""

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.results import OutputSnapshot
from ..core.manifest import canonical_bytes
from ..sources.base import checked_paths,read_limited
from ..sources.bundle import file_records,read_verified
from ..worker.receipt import digest_file,write_once


def snapshot_outputs(handle,site):
    from ..executors.loader import load_executor
    observation=load_executor(site).query(handle)
    if not observation.identity_verified or observation.execution_state not in {'COMPLETED','FAILED','CANCELLED'}:
        raise ControlError('RESULT_UNVERIFIED','native terminal identity is not verified')
    root=Path(handle.run_root)
    launch=decode_json((root/'approved-plan.json').read_bytes())
    approved=launch['approved'];input_root=Path(approved['input_root'])
    manifest_raw=(input_root.parent/'manifest.json').read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest()!=approved['manifest_sha256']:
        raise ControlError('RESULT_UNVERIFIED','input manifest changed')
    manifest=decode_json(manifest_raw)
    inputs=read_verified(input_root,manifest['files'])
    origins={'stdout.log':root/'stdout.log','stderr.log':root/'stderr.log'}
    work=Path(approved['plan']['cwd'])
    if work.is_symlink() or not work.resolve().is_relative_to(root.resolve()):
        raise ControlError('RESULT_UNVERIFIED','work root escaped the verified run')
    outputs=approved['plan']['outputs']
    if not isinstance(outputs,list) or not all(isinstance(name,str) for name in outputs):
        raise ControlError('RESULT_UNVERIFIED','invalid output declaration')
    checked_paths([name for name in outputs if name!='*'])
    if work.exists():
        for path in work.rglob('*'):
            mode=path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ControlError('RESULT_UNVERIFIED','output links and special files are rejected')
            if path.is_file():
                name=path.relative_to(work).as_posix();checked_paths([name])
                if name in origins or name=='task-manifest.json' or name.startswith('inputs/'):
                    raise ControlError('RESULT_UNVERIFIED','reserved output path collision')
                if '*' in outputs or name in outputs:origins[name]=path
    total=sum(p.stat().st_size for p in origins.values())+sum(map(len,inputs.values()))+len(manifest_raw)
    if len(origins)+len(inputs)>site.limits.get('max_output_files',4096) or total>site.limits.get('max_output_bytes',268435456):
        raise ControlError('RESULT_UNVERIFIED','output snapshot exceeds site budget')
    payload={};before={}
    for name,path in origins.items():
        if path.is_symlink():raise ControlError('RESULT_UNVERIFIED','linked output rejected')
        before[name]=(path.stat().st_dev,path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns)
        payload[name]=read_limited(path,before[name][2],code="RESULT_UNVERIFIED")
    for name,path in origins.items():
        after=(path.stat().st_dev,path.stat().st_ino,path.stat().st_size,path.stat().st_mtime_ns)
        if before[name]!=after or hashlib.sha256(read_limited(path,len(payload[name]),code='RESULT_UNVERIFIED')).hexdigest()!=hashlib.sha256(payload[name]).hexdigest():
            raise ControlError('RESULT_UNVERIFIED','output changed while snapshotting')
    payload.update({'inputs/'+name:raw for name,raw in inputs.items()})
    payload['task-manifest.json']=manifest_raw
    records=file_records(payload)
    terminal={**observation.evidence,'execution_state':observation.execution_state,'integrity':'VERIFIED'}
    identity={'files':records,'terminal':terminal,'manifest_sha256':approved['manifest_sha256']}
    digest=hashlib.sha256(canonical_bytes(identity)).hexdigest()
    target=site.root/'snapshots'/digest
    for name,raw in payload.items():
        write_once(target/name,raw);(target/name).chmod(0o400)
    write_once(target/'snapshot.json',canonical_bytes(identity))
    return OutputSnapshot(target,records,approved['manifest_sha256'],terminal)
