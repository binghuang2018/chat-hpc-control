import importlib
import pytest


def api():
    try:return importlib.import_module('chat_hpc_control.clients.session')
    except ModuleNotFoundError:pytest.fail('durable client session missing')


def test_persistent_key_and_explicit_rerun(tmp_path):
    path=tmp_path/'session.db'
    store=api().ClientSessionStore.open(path)
    store.bind_identity('example','alice');store.begin_request('human-1','run this calculation')
    key=store.reserve_intent('human-1','primary','a'*64)
    store.record_run('human-1','run-1');store.close()
    store=api().ClientSessionStore.open(path)
    try:
        store.bind_identity('example','alice');store.begin_request('human-1','run this calculation')
        assert store.reserve_intent('human-1','primary','a'*64)==key
        with pytest.raises(Exception):store.reserve_intent('human-1','primary','b'*64)
        with pytest.raises(Exception):store.bind_identity('example','mallory')
        store.begin_request('human-2','run the same calculation again')
        with pytest.raises(Exception):store.reserve_intent('human-2','primary','a'*64)
        store.begin_request('human-3','rerun run-1',rerun_of='run-1')
        assert store.reserve_intent('human-3','primary','a'*64)!=key
    finally:store.close()


def test_parallel_duplicate_reservations_share_one_key(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store=api().ClientSessionStore.open(tmp_path/'parallel.db')
    store.bind_identity('example','alice');store.begin_request('human-1','calculate once')
    try:
        with ThreadPoolExecutor(8) as pool:
            keys=list(pool.map(lambda _:store.reserve_intent('human-1','primary','a'*64),range(32)))
        assert len(set(keys))==1
    finally:store.close()
