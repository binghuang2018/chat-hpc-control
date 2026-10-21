import base64,hashlib,importlib
import pytest


def test_ref_resolves_once_and_verifies_blob():
    try:reader_api=importlib.import_module('chat_hpc_control.sources.github_reader')
    except ModuleNotFoundError:pytest.fail('GitHub source reader missing')
    data=b'print(1)\n';blob=hashlib.sha1(b'blob 9\0'+data).hexdigest();calls=[]
    def get(path,params=None):
        calls.append((path,params))
        if '/commits/' in path:return {'sha':'a'*40}
        if '/git/trees/' in path:return {'truncated':False,'tree':[{'path':'job.py','type':'blob','mode':'100644','sha':blob,'size':9}]}
        if '/git/blobs/' in path:return {'sha':blob,'size':9,'encoding':'base64','content':base64.b64encode(data).decode()}
        raise AssertionError(path)
    reader=reader_api.GitHubReader(get,{'https://github.com/example/qc'})
    commit=reader.resolve_ref('https://github.com/example/qc','main')
    assert reader.resolve_ref('https://github.com/example/qc','main')==commit
    assert reader.read_blob('https://github.com/example/qc',commit,'job.py')==(blob,data)
    assert sum('/commits/' in p for p,_ in calls)==1
    with pytest.raises(Exception):reader.read_blob('https://github.com/other/qc',commit,'job.py')


def test_github_reader_rejects_symlinks_and_tampered_blob():
    try:module=importlib.import_module('chat_hpc_control.sources.github_reader')
    except ModuleNotFoundError:pytest.fail('GitHub source reader missing')
    def get(path,params=None):
        if '/git/trees/' in path:return {'truncated':False,'tree':[{'path':'job.py','type':'blob','mode':'120000','sha':'b'*40,'size':1}]}
        raise AssertionError('symlink was followed')
    reader=module.GitHubReader(get,{'https://github.com/example/qc'})
    with pytest.raises(Exception):reader.read_blob('https://github.com/example/qc','a'*40,'job.py')


def test_staged_git_snapshot_is_credential_free_and_verified(tmp_path,sample_task):
    from dataclasses import replace
    import json
    from chat_hpc_control.contracts.codec import parse_task
    from chat_hpc_control.contracts.config import SiteConfig,ExecutorConfig
    from chat_hpc_control.sources.base import SourceResolver
    from chat_hpc_control.sources.staged_git import stage_task,cache_root
    repository='https://github.com/example/qc'
    site=SiteConfig('example',tmp_path,{}, {},ExecutorConfig('local','example'),repositories={repository:str(tmp_path/'no-mirror')})
    task=deepcopy_task=json.loads(json.dumps(sample_task))
    task['source']={'kind':'git','repository':repository,'ref':'main','files':['job.py']}
    task['entrypoint']='job.py'
    data=b'print(1)\n'
    class Reader:
        def resolve_ref(self,repo,ref):return 'a'*40
        def read_blob(self,repo,commit,path):return hashlib.sha1(b'blob 9\0'+data).hexdigest(),data
    pinned=stage_task(parse_task(json.dumps(task).encode()),site,Reader())
    resolved=SourceResolver().resolve(pinned,site)
    assert resolved.files=={'job.py':data} and resolved.task.source['ref']=='a'*40
    cached=cache_root(site,repository,'a'*40)/'files/job.py'
    cached.write_bytes(b'changed')
    with pytest.raises(Exception):SourceResolver().resolve(pinned,site)
