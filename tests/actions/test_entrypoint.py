from copy import deepcopy
from dataclasses import replace
import importlib,json
import pytest
from tests.transports.test_github import github_case
from chat_hpc_control.contracts.tools import ToolResponse


def test_duplicate_and_edited_issue_intent(github_case):
    try:api=importlib.import_module('chat_hpc_control.transports.github')
    except ModuleNotFoundError:pytest.fail('GitHub gateway missing')
    event,issue,site=github_case
    calls=[]
    def dispatch(call,context):
        calls.append(call)
        if call.name=='validate_task':return ToolResponse('v',True,{'valid':True,'task':call.arguments['task'],'manifest_sha256':'a'*64})
        return ToolResponse('s',True,{'run_id':'same-run'})
    gateway=api.GitHubGateway(site,lambda n:issue,dispatch)
    one=gateway.dispatch(event);two=gateway.dispatch(event)
    assert one.data==two.data
    submissions=[c for c in calls if c.name=='submit_task']
    assert len(submissions)==2 and submissions[0].arguments==submissions[1].arguments
    assert submissions[0].arguments['idempotency_key']=='github:example/qc-inputs:issue:7'
    assert not any('token' in json.dumps(c.arguments).lower() for c in calls)
    issue['body']=issue['body'].replace('water-001','water-002')
    with pytest.raises(Exception):gateway.dispatch(event)
