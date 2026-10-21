"""Self-contained clean-site synthetic quickstart using public CLI commands."""

from importlib.resources import files
import io
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tarfile
import time
from .contracts.codec import decode_json
from .contracts.errors import ControlError
from .worker.receipt import write_once

JOB=b'''"""Synthetic data, not a quantum calculation."""
import json
from pathlib import Path
Path('records.json').write_text(json.dumps({'records':[{'record_id':'demo-0','energy':0.0,'synthetic':True}]}))
print('synthetic demo completed')
'''


def run_demo(root,*,resume=False,wait_seconds=120):
    if sys.platform!='linux' or platform.machine()!='x86_64':
        raise ControlError('CAPABILITY_UNSUPPORTED','native demo requires Linux x86_64; macOS supports core/client use')
    root=Path(root)
    if (not root.is_absolute() or root.is_symlink() or any(ord(c)<32 for c in str(root))
            or len(os.fsencode(root/'state/broker.sock'))>=104):
        raise ControlError('SCHEMA_INVALID','choose an explicit short absolute private demo root')
    if type(wait_seconds)!=int or not 1<=wait_seconds<=600:raise ControlError('SCHEMA_INVALID','invalid demo control wait')
    marker=root/'demo-owner.json'
    if root.exists() and any(root.iterdir()):
        if not resume or not marker.is_file() or marker.is_symlink() or decode_json(marker.read_bytes())!={'schema':'chat-hpc-control/demo-owner/v1','uid':os.getuid()}:
            raise ControlError('AUTH_DENIED','nonempty directory is not this user\'s resumable demo')
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    write_once(marker,json.dumps({'schema':'chat-hpc-control/demo-owner/v1','uid':os.getuid()}).encode())
    for name in ('home','tmp'):(root/name).mkdir(mode=0o700,exist_ok=True)
    site=root/'site.toml'
    if not site.exists():
        template=files('chat_hpc_control').joinpath('templates/site-demo.toml.in').read_text()
        for key,value in {'@ROOT@':json.dumps(str(root/'state')),'@PYTHON@':json.dumps(sys.executable),
                          '@UID@':str(os.getuid()),'@CPUS@':str(min(2,len(os.sched_getaffinity(0))))}.items():template=template.replace(key,value)
        write_once(site,template.encode())
    from .core.config import load_site
    configured=load_site(site)
    if (site.is_symlink() or configured.site_id!='example-demo' or configured.root!=root/'state'
            or set(configured.engines)!={'demo'} or configured.executor.kind!='local'
            or Path(configured.engines['demo'].executable).resolve()!=Path(sys.executable).resolve()
            or configured.engines['demo'].version_args!=('--version',)
            or configured.engines['demo'].environment or configured.engines['demo'].mpi_argv
            or configured.repositories or configured.gateway_uids):
        raise ControlError('AUTH_DENIED','resume configuration is not this isolated synthetic demo site')
    environment={'PATH':os.defpath,'HOME':str(root/'home'),'TMPDIR':str(root/'tmp'),'LANG':'C.UTF-8'}
    prefix=[sys.executable,'-I','-m','chat_hpc_control.cli','--site',str(site)]
    commands=[]
    def command(argv):
        commands.append(argv)
        result=subprocess.run([*prefix,*argv],env=environment,cwd=root,capture_output=True,timeout=45)
        data=decode_json(result.stdout)
        if result.returncode or data.get('ok') is not True:
            error=data.get('error') or {};raise ControlError(error.get('code','DEMO_CONTROL_FAILED'),error.get('message','demo control call failed'))
        return data['data']
    log=open(root/'broker.log','ab');os.chmod(root/'broker.log',0o600)
    broker=subprocess.Popen([*prefix,'broker','serve'],env=environment,cwd=root,stdin=subprocess.DEVNULL,
                            stdout=log,stderr=log,start_new_session=True,close_fds=True)
    try:
        deadline=time.monotonic()+30
        while not (root/'state/broker.sock').exists():
            if broker.poll() is not None or time.monotonic()>deadline:
                raise ControlError('BROKER_UNAVAILABLE','demo broker did not start; inspect its private broker.log')
            time.sleep(.05)
        checkpoint=root/'submission.json'
        if checkpoint.exists():submission=decode_json(checkpoint.read_bytes())
        else:
            archive=root/'input.tar'
            with tarfile.open(archive,'w') as out:
                member=tarfile.TarInfo('job.py');member.size=len(JOB);out.addfile(member,io.BytesIO(JOB))
            bundle=command(['bundle','import',str(archive)])['bundle_id']
            task={'schema':'chat-hpc-control/task/v1','task_id':'demo-synthetic','engine_id':'demo','engine_options':{},
                  'source':{'kind':'bundle','bundle_id':bundle},'entrypoint':'job.py',
                  'resources':{'cpus':1,'memory_mib':64,'walltime_seconds':None},'expected_results':None}
            task_path=root/'task.json';write_once(task_path,json.dumps(task).encode())
            validated=command(['validate','--task',str(task_path)])
            submission={'task':validated['task'],'manifest_sha256':validated['manifest_sha256'],'idempotency_key':'quickstart:demo:v1'}
            write_once(checkpoint,json.dumps(submission).encode())
        approved=root/'validated-task.json';write_once(approved,json.dumps(submission['task']).encode())
        receipt=command(['submit','--task',str(approved),'--expected-manifest',submission['manifest_sha256'],
                         '--idempotency-key',submission['idempotency_key']])
        run_id=receipt['run_id'];deadline=time.monotonic()+wait_seconds
        while time.monotonic()<deadline:
            status=command(['status',run_id])
            if status['collection_state']=='COLLECTED':break
            time.sleep(.2)
        else:raise ControlError('RESULT_UNVERIFIED','demo control wait ended; reuse demo --resume; computation was not cancelled',evidence_refs=[run_id])
        result=command(['results',run_id,'--fields','record_id','energy','evidence_level'])
        if status['execution_state']!='COMPLETED' or not result['collection_id']:
            raise ControlError('RESULT_UNVERIFIED','synthetic demo did not complete and collect')
        evidence={'run_id':run_id,'execution_state':status['execution_state'],'collection_id':result['collection_id'],
                  'records':result['records'],'synthetic':True,'data_ready':result['summary']['data_ready'],
                  'scientific_acceptance':result['summary']['scientific_acceptance']}
        (root/'quickstart-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
        os.chmod(root/'quickstart-evidence.json',0o600)
        return evidence
    finally:
        (root/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');os.chmod(root/'commands.json',0o600)
        if broker.poll() is None:
            broker.send_signal(signal.SIGTERM)
            try:broker.wait(timeout=10)
            except subprocess.TimeoutExpired:broker.kill();broker.wait()
        log.close()
