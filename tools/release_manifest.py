"""Build a local candidate manifest from artifacts and independently captured evidence.

Evidence is a JSON record with name, status, command, environment, versions,
exit_code, log (relative to evidence directory), summary and gaps. A PASS needs
actual nonempty log bytes and successful process status. This records evidence;
it cannot substitute for reviewing the semantic assertion in summary.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def build_release_manifest(dist_dir:Path,evidence_dir:Path)->dict:
    artifacts=[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in sorted(dist_dir.iterdir()) if p.is_file() and (p.name.endswith('.whl') or p.name.endswith('.tar.gz'))]
    if not artifacts:raise ValueError('no wheel/sdist artifacts')
    records=[]
    for path in sorted(evidence_dir.glob('*.json')):
        record=json.loads(path.read_text())
        if record.get('status') not in {'PASS','NOT_RUN','FAIL'}:raise ValueError('unknown evidence status')
        if record['status']=='PASS':
            if any(not record.get(k) for k in ('name','command','environment','versions','log','log_sha256','summary')) or record.get('exit_code')!=0:
                raise ValueError('PASS requires command, versions, environment, successful result and log')
            log=(evidence_dir/record['log']).resolve()
            if not log.is_relative_to(evidence_dir.resolve()) or not log.is_file() or not log.stat().st_size:raise ValueError('missing/escaped evidence log')
            if record['log_sha256']!=sha(log):raise ValueError('evidence log digest changed')
        elif not record.get('gaps'):raise ValueError('unexecuted/failed evidence needs explicit gap')
        records.append(record)
    if not records:raise ValueError('no evidence records')
    root=Path(__file__).resolve().parents[1]
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    return {'release':'0.1.0','distribution':'chat-hpc-control','candidate_only':True,'source_commit':git('rev-parse','HEAD'),
            'source_dirty':bool(git('status','--porcelain')),'protocols':{'task':1,'result':1,'plugin_api':'1.0','tool_response':1},
            'artifacts':artifacts,'evidence':records,'published':False,'production_migrated':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dist',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();data=build_release_manifest(args.dist,args.evidence)
    args.output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
