import hashlib,importlib
import pytest

class FakeGitHub:
    def __init__(self):
        self.head='0'*40;self.commits={self.head:{'files':{},'parent':None}};self.trees={};self.created=0;self.lost=False;self.forces=[]
    def get_ref(self,branch):return self.head
    def create_tree(self,base,files):
        digest=hashlib.sha1(b''.join(k.encode()+v for k,v in sorted(files.items()))).hexdigest()
        self.trees[digest]={**self.commits[base]['files'],**files};return digest
    def create_commit(self,base,tree,message):
        digest=hashlib.sha1((base+tree+message).encode()).hexdigest()
        self.commits[digest]={'files':self.trees[tree],'parent':base};self.created+=1;return digest
    def update_ref(self,branch,commit,*,force):
        self.forces.append(force)
        if self.commits[commit]['parent']!=self.head:raise RuntimeError('non-fast-forward')
        self.head=commit
        if self.lost:self.lost=False;raise ConnectionError('synthetic response loss after ref update')
    def read_files(self,commit,prefix):
        return {k[len(prefix)+1:]:v for k,v in self.commits[commit]['files'].items() if k.startswith(prefix+'/')}
    def is_ancestor(self,ancestor,head):
        while head:
            if head==ancestor:return True
            head=self.commits[head]['parent']
        return False


def api():
    try:return importlib.import_module('chat_hpc_control.publishers.github')
    except ModuleNotFoundError:pytest.fail('GitHub publisher missing')


def test_fixed_commit_and_no_force_push(publish_case):
    ref,snapshots,root=publish_case;remote=FakeGitHub()
    publisher=api().GitHubPublisher(remote,repository='example/results',branch='results',state_root=root/'publish-state',snapshot_store=snapshots)
    one=publisher.publish(ref);two=publisher.publish(ref)
    assert one.state==two.state=='PUBLISHED'
    assert one.identity['commit']==two.identity['commit'] and remote.created==1
    assert remote.forces==[False]


def test_lost_update_response_is_read_back(publish_case):
    ref,snapshots,root=publish_case;remote=FakeGitHub();remote.lost=True
    publisher=api().GitHubPublisher(remote,repository='example/results',branch='results',state_root=root/'publish-state',snapshot_store=snapshots)
    one=publisher.publish(ref)
    assert one.state=='PUBLISH_UNKNOWN'
    recovered=publisher.reconcile_publish(one)
    assert recovered.state=='PUBLISHED' and remote.created==1
    assert publisher.publish(ref)==recovered


def test_concurrent_branch_change_never_forces_update(publish_case):
    ref,snapshots,root=publish_case;remote=FakeGitHub()
    original=remote.update_ref
    def conflict(branch,commit,*,force):
        remote.commits['f'*40]={'files':{},'parent':'0'*40};remote.head='f'*40
        return original(branch,commit,force=force)
    remote.update_ref=conflict
    publisher=api().GitHubPublisher(remote,repository='example/results',branch='results',state_root=root/'state',snapshot_store=snapshots)
    receipt=publisher.publish(ref)
    assert receipt.state=='PUBLISH_UNKNOWN' and remote.head=='f'*40 and remote.forces==[False]
    assert publisher.publish(ref).state=='PUBLISH_UNKNOWN' and remote.created==1


def test_parallel_publish_cannot_create_two_commits(publish_case):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    ref,snapshots,root=publish_case;remote=FakeGitHub();entered=threading.Event();release=threading.Event()
    original=remote.create_tree
    def slow(base,files):
        entered.set();assert release.wait(3)
        return original(base,files)
    remote.create_tree=slow
    publisher=api().GitHubPublisher(remote,repository='example/results',branch='results',state_root=root/'state',snapshot_store=snapshots)
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(publisher.publish,ref);assert entered.wait(3)
        second=pool.submit(publisher.publish,ref)
        try:
            outcome=second.result(timeout=1)
            assert outcome.state=='PUBLISH_UNKNOWN'
        except Exception as exc:
            assert getattr(exc,'code',None)=='PUBLISH_UNKNOWN',exc
        finally:release.set()
        assert first.result(timeout=3).state=='PUBLISHED'
    assert remote.created==1


def test_first_reservation_race_has_one_external_writer(publish_case):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    ref,snapshots,root=publish_case;remote=FakeGitHub();barrier=threading.Barrier(2)
    publisher=api().GitHubPublisher(remote,repository='example/results',branch='results',state_root=root/'state',snapshot_store=snapshots)
    original=publisher._save
    def before_save(collection_id,data):
        if data['phase']=='RESERVED':
            try:barrier.wait(.2)
            except threading.BrokenBarrierError:pass
        original(collection_id,data)
    publisher._save=before_save
    def submit():
        try:return publisher.publish(ref).state
        except Exception as exc:
            assert getattr(exc,'code',None)=='PUBLISH_UNKNOWN'
            return 'PUBLISH_UNKNOWN'
    with ThreadPoolExecutor(2) as pool:states=list(pool.map(lambda _:submit(),range(2)))
    assert 'PUBLISHED' in states and remote.created==1
