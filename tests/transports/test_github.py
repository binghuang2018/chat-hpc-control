from copy import deepcopy
from dataclasses import replace
import importlib,json
import pytest
from chat_hpc_control.contracts.config import SiteConfig,ExecutorConfig

@pytest.fixture
def github_case(sample_task,tmp_path):
    body='<!-- CHAT_HPC_CONTROL_REQUEST_V1 -->\n'+json.dumps({'version':1,'task':sample_task})
    issue={'id':100,'number':7,'user':{'id':42},'body':body,'labels':[{'name':'qc-request'}]}
    event={'action':'labeled','repository':{'id':9,'full_name':'example/qc-inputs'},'sender':{'id':43},'issue':deepcopy(issue)}
    scopes=['tasks:validate','tasks:submit','tasks:read','results:read']
    policy={'scopes':scopes,'engines':['pyscf'],'repositories':['https://github.com/example/qc-inputs']}
    site=SiteConfig('example',tmp_path,{'alice':policy,'maintainer':policy},{},ExecutorConfig('local','test'),
      gateway_uids=(123,),settings={'github_repository':'example/qc-inputs','github_repository_id':9,
      'github_principals':{'42':'alice','43':'maintainer'}})
    return event,issue,site


def api():
    try:return importlib.import_module('chat_hpc_control.transports.github')
    except ModuleNotFoundError:pytest.fail('GitHub transport missing')


def test_verified_author_and_actor(github_case):
    call,ctx=api().parse_issue(*github_case)
    assert call.name=='validate_task'
    assert ctx.principal=='alice' and ctx.author=='alice' and ctx.actor=='maintainer'
    assert ctx.transport=='github'


@pytest.mark.parametrize('mutation',['repo','author','actor','pr','id','label','body'])
def test_reject_untrusted_event(github_case,mutation):
    event,issue,site=github_case
    if mutation=='repo':event['repository']['id']=10
    if mutation=='author':issue['user']['id']=99
    if mutation=='actor':event['sender']['id']=99
    if mutation=='pr':issue['pull_request']={}
    if mutation=='id':issue['id']=101
    if mutation=='label':issue['labels']=[]
    if mutation=='body':issue['body']+='\nnot json'
    with pytest.raises(Exception):api().parse_issue(event,issue,site)


def test_stale_authorized_event_cannot_authorize_a_later_body(github_case):
    event,issue,site=github_case
    payload=json.loads(issue['body'].split('-->',1)[1]);payload['task']['resources']['cpus']=8
    issue['body']='<!-- CHAT_HPC_CONTROL_REQUEST_V1 -->\n'+json.dumps(payload)
    with pytest.raises(Exception,match='AUTH_DENIED'):api().parse_issue(event,issue,site)


def test_request_label_must_exist_in_authenticated_event(github_case):
    event,issue,site=github_case;event['issue']['labels']=[]
    with pytest.raises(Exception,match='AUTH_DENIED'):api().parse_issue(event,issue,site)
