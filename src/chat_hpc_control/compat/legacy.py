"""Retain original legacy bytes, algorithms and digests without rekeying."""

import base64
import hashlib
import json
from pathlib import Path
import re
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.results import CompatibilityReport
from ..sources.base import checked_paths

LEGACY_MARKER='<!-- CHATGPT_QC_REQUEST_V1 -->'


def wrap_legacy(raw_manifest,digest_algorithm,claimed_digest):
    issues=[];obj={};verified=False
    try:obj=decode_json(raw_manifest)
    except ValueError:issues.append({'code':'LEGACY_MANIFEST_UNREADABLE'})
    try:
        if digest_algorithm=='hpc-control-qc-json-v1':
            # Legacy rule: ASCII-escaped, sorted compact JSON, trailing newline.
            # This checks the old identity; the original bytes are kept below.
            encoded=json.dumps(obj,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
            actual=hashlib.sha256(encoded).hexdigest()
        elif digest_algorithm in {'sha256','sha256-bytes'}:actual=hashlib.sha256(raw_manifest).hexdigest()
        else:actual=None;issues.append({'code':'LEGACY_DIGEST_ALGORITHM_UNSUPPORTED'})
        if actual is not None:
            verified=actual==claimed_digest and not issues
            if not verified:issues.append({'code':'LEGACY_DIGEST_MISMATCH'})
    except (ValueError,TypeError):issues.append({'code':'LEGACY_DIGEST_UNVERIFIED'})
    return {'schema':'chat-hpc-control/legacy-envelope/v1','legacy_schema':obj.get('schema'),
            'legacy_version':obj.get('version'),'legacy_digest':{'algorithm':digest_algorithm,'value':claimed_digest},
            'source_ref':obj.get('source_ref',obj.get('source')),'raw_base64':base64.b64encode(raw_manifest).decode(),
            'storage_sha256':hashlib.sha256(raw_manifest).hexdigest(),'digest_verified':verified,
            'native_identity':'UNVERIFIED','adoptable':False,'issues':issues}


def _read(root,name):
    checked_paths([name]);path=root/name
    if root.is_symlink() or any(parent.is_symlink() for parent in [path,*path.parents] if parent.is_relative_to(root)):
        raise ControlError('RESULT_UNVERIFIED','legacy snapshot contains links')
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size>8*1024*1024:
        raise ControlError('RESULT_UNVERIFIED','legacy file is not bounded and regular')
    return path.read_bytes()


def inspect_legacy(snapshot_root):
    root=Path(snapshot_root);records=[];issues=[];observed={}
    try:
        raw=_read(root,'legacy-index.json');observed['legacy-index.json']=raw
        index=decode_json(raw)
        if index.get('schema')!='hpc-control/offline-export/v1' or index.get('offline') is not True:
            raise ControlError('RESULT_UNVERIFIED','explicit offline export index is required')
        if not isinstance(index.get('records'),list) or len(index['records'])>1024:
            raise ControlError('RESULT_UNVERIFIED','legacy export record budget exceeded')
        for entry in index['records']:
            try:
                name=entry['manifest_file'];raw=_read(root,name);observed[name]=raw
                envelope=wrap_legacy(raw,entry['digest_algorithm'],entry['claimed_digest'])
                if not isinstance(entry['task_id'],str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',entry['task_id']):
                    raise ValueError('legacy task identity')
                record={'task_id':entry['task_id'],'kind':entry['kind'],'envelope':envelope,
                        'legacy_state':entry.get('legacy_state','UNKNOWN'),'legacy_job_id':entry.get('legacy_job_id'),
                        'native_identity':'UNVERIFIED','adoptable':False,'data_ready':False}
                records.append(record)
                issues.extend({'task_id':entry['task_id'],**issue} for issue in envelope['issues'])
            except (OSError,ValueError,KeyError,TypeError):issues.append({'code':'LEGACY_RECORD_UNVERIFIED'})
        if any(_read(root,name)!=raw for name,raw in observed.items()):
            issues.append({'code':'OFFLINE_SNAPSHOT_CHANGED_DURING_READ'})
    except (OSError,ValueError,KeyError,TypeError):issues.append({'code':'LEGACY_SNAPSHOT_UNVERIFIED'})
    return CompatibilityReport(records,issues)


def resolve_legacy_issue(issue,report):
    body=issue.get('body','')
    if not isinstance(body,str) or not body.startswith(LEGACY_MARKER):raise ControlError('SCHEMA_INVALID','not a legacy QC Issue')
    payload=decode_json(body[len(LEGACY_MARKER):].strip().encode())
    if (set(payload)!={'version','kind','task_id'} or type(payload['version'])!=int or payload['version']!=1
            or payload['kind'] not in {'pyscf','orca','molpro'} or not isinstance(payload['task_id'],str)
            or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',payload['task_id'])):
        raise ControlError('SCHEMA_INVALID','unsupported legacy QC Issue envelope')
    matches=[r for r in report.records if r['task_id']==payload['task_id'] and r['kind']==payload['kind']]
    result={'mode':'READ_ONLY_LEGACY','task_id':payload['task_id'],'kind':payload['kind'],
            'adoptable':False,'native_identity':'UNVERIFIED','new_submission_created':False,'data_ready':False,
            'issues':report.issues}
    if len(matches)==1:
        old=matches[0];result.update(legacy_digest=old['envelope']['legacy_digest'],
            digest_verified=old['envelope']['digest_verified'],legacy_state=old['legacy_state'])
    else:result['issues']=[*report.issues,{'code':'LEGACY_MAPPING_MISSING_OR_AMBIGUOUS'}]
    return result
