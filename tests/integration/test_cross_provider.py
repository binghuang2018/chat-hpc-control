from dataclasses import replace
import importlib
import pytest
from tests.clients.helpers import fake_adapter,wire
from tests.clients.test_tool_loop import args
from tests.core.test_idempotency import setup_broker


def test_retry_and_provider_switch_reuses_same_authenticated_run(setup_broker,tmp_path):
    try:
        from chat_hpc_control.clients.session import ClientSessionStore
        from chat_hpc_control.clients.loop import run_turn
    except ModuleNotFoundError:pytest.fail('cross-provider intent loop missing')
    broker,task,context,store,engine,executor=setup_broker
    from chat_hpc_control.core.service import ToolService
    service=ToolService(broker)
    client=ClientSessionStore.open(tmp_path/'client.db');client.bind_identity(context.site_id,context.principal)
    client.begin_request('human-1','calculate once')
    validated=broker.validate(task,context)
    validate=('validate_task',{'site_id':context.site_id,'task':task.to_dict()})
    submit_args={'site_id':context.site_id,'task':task.to_dict(),'expected_manifest_sha256':validated.manifest_sha256,
                 'idempotency_key':'model-changes-this','rerun_of':None}
    submit=('submit_task',submit_args)
    try:
        first=run_turn(fake_adapter('openai',[wire('openai',[validate,submit]),ConnectionError('synthetic API disconnect')]),
                       client,'calculate once',lambda call:service.handle(call,context))
        assert first['state']=='CLIENT_REQUEST_UNKNOWN' and len(executor.submissions)==1
        for name in ('anthropic','gemini'):
            second=run_turn(fake_adapter(name,[wire(name,[submit]),wire(name)]),client,'calculate once',lambda call:service.handle(call,context))
            assert second['state']=='COMPLETED' and second['run_ids']==first['run_ids']
        assert len(executor.submissions)==1
    finally:client.close()
