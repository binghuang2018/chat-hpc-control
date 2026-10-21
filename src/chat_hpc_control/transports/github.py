"""Trusted Actions event adapter; this is not an unsigned webhook listener."""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
from ..contracts.auth import PeerIdentity
from ..contracts.codec import decode_json,parse_task
from ..contracts.errors import ControlError
from ..contracts.tools import ToolCall
from ..core.auth import context_from_peer
from ..core.manifest import canonical_bytes
from ..worker.receipt import write_once

MARKER='<!-- CHAT_HPC_CONTROL_REQUEST_V1 -->'


def _issue_context(event,fetched_issue,site):
    try:
        settings=site.settings;repository=settings['github_repository']
        if (event.get('action') not in {'opened','edited','labeled','reopened'}
                or event['repository']['full_name']!=repository
                or event['repository']['id']!=settings['github_repository_id']
                or type(event['repository']['id'])!=int or 'pull_request' in fetched_issue
                or 'pull_request' in event['issue'] or fetched_issue['number']!=event['issue']['number']
                or fetched_issue['id']!=event['issue']['id'] or type(fetched_issue['number'])!=int or fetched_issue['number']<=0
                or type(fetched_issue['user']['id'])!=int or fetched_issue['user']['id']<=0
                or type(event['sender']['id'])!=int or event['sender']['id']<=0
                or fetched_issue['user']['id']!=event['issue']['user']['id']
                or fetched_issue['body']!=event['issue']['body']
                or not any(label['name']=='qc-request' for label in event['issue']['labels'])
                or not any(label['name']=='qc-request' for label in fetched_issue['labels'])):raise ValueError('event binding')
        users=settings['github_principals']
        author=users[str(fetched_issue['user']['id'])];actor=users[str(event['sender']['id'])]
        scopes=sorted(set(site.principals[author]['scopes'])&set(site.principals[actor]['scopes']))
        identity={'principal':author,'author':author,'actor':actor,'transport':'github','site_id':site.site_id,'scopes':scopes}
        context=context_from_peer(PeerIdentity(site.gateway_uids[0],0,0),{'context':identity},site)
        return context
    except (KeyError,IndexError,TypeError,ValueError) as exc:
        raise ControlError('AUTH_DENIED','GitHub event, fetched Issue, or stable user identity was rejected') from exc


def parse_issue(event,fetched_issue,site):
    context=_issue_context(event,fetched_issue,site)
    try:
        body=fetched_issue['body']
        if not isinstance(body,str) or not body.startswith(MARKER) or body.count(MARKER)!=1:raise ValueError('marker')
        payload=decode_json(body[len(MARKER):].strip().encode())
        if set(payload)!={'version','task'} or type(payload['version'])!=int or payload['version']!=1:raise ValueError('envelope')
        task=parse_task(json.dumps(payload['task']).encode())
        if task.source['kind']=='git' and task.source['repository']!='https://github.com/'+site.settings['github_repository']:
            raise ValueError('task repository')
        return ToolCall('validate_task',{'site_id':site.site_id,'task':task.to_dict()}),context
    except (KeyError,IndexError,TypeError,ValueError) as exc:
        raise ControlError('AUTH_DENIED','GitHub request body was rejected') from exc


class GitHubGateway:
    def __init__(self,site,fetch_issue,dispatch,reader=None):
        self.site,self.fetch_issue,self.call_tool,self.reader=site,fetch_issue,dispatch,reader

    def dispatch(self,event):
        number=event.get('issue',{}).get('number')
        if type(number)!=int or number<=0:raise ControlError('AUTH_DENIED','not a bound Issue event')
        issue=self.fetch_issue(number)
        from ..compat.legacy import LEGACY_MARKER,inspect_legacy,resolve_legacy_issue
        if isinstance(issue.get('body'),str) and issue['body'].startswith(LEGACY_MARKER):
            from ..core.auth import authorize
            from ..contracts.results import CompatibilityReport
            from ..contracts.tools import ToolResponse
            import uuid
            context=_issue_context(event,issue,self.site);authorize(context,'tasks:read',None)
            configured=self.site.settings.get('legacy_snapshot')
            report=inspect_legacy(Path(configured)) if configured else CompatibilityReport([], [{'code':'LEGACY_SNAPSHOT_NOT_CONFIGURED'}])
            return ToolResponse(str(uuid.uuid4()),True,resolve_legacy_issue(issue,report))
        call,context=parse_issue(event,issue,self.site)
        repository=self.site.settings['github_repository']
        intent_path=self.site.root/'gateway-intents'/('github-'+str(self.site.settings['github_repository_id'])+'-'+str(number)+'.json')
        body_sha=hashlib.sha256(issue['body'].encode()).hexdigest()
        if intent_path.exists():
            saved=decode_json(intent_path.read_bytes())
            if saved['body_sha256']!=body_sha or saved['principal']!=context.principal:
                raise ControlError('IDEMPOTENCY_CONFLICT','Issue was edited after its first frozen intent; create a new Issue')
            submit=ToolCall('submit_task',saved['submission'])
        else:
            if call.arguments['task']['source']['kind']=='git' and self.reader is not None:
                from ..sources.staged_git import stage_task
                task=stage_task(parse_task(json.dumps(call.arguments['task']).encode()),self.site,self.reader)
                call=ToolCall(call.name,{'site_id':self.site.site_id,'task':task.to_dict()})
            validated=self.call_tool(call,context)
            if not validated.ok:return validated
            params={'site_id':self.site.site_id,'task':validated.data['task'],
                    'expected_manifest_sha256':validated.data['manifest_sha256'],
                    'idempotency_key':f'github:{repository}:issue:{number}','rerun_of':None}
            write_once(intent_path,canonical_bytes({'body_sha256':body_sha,'principal':context.principal,'submission':params}))
            submit=ToolCall('submit_task',params)
        return self.call_tool(submit,context)


class GitHubApi:
    def __init__(self,token):
        if not token:raise ControlError('AUTH_DENIED','gateway GitHub token is missing')
        try:import httpx
        except ImportError as exc:raise ControlError('CAPABILITY_UNSUPPORTED','install chat-hpc-control[github] on the gateway') from exc
        self.client=httpx.Client(base_url='https://api.github.com',headers={'Authorization':'Bearer '+token,
            'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},timeout=20,follow_redirects=False)

    def get(self,path,params=None):
        if not path.startswith('/repos/') or '://' in path:raise ControlError('SOURCE_NOT_ALLOWED','API path rejected')
        try:
            with self.client.stream('GET',path,params=params) as response:
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>96*1024*1024:raise ValueError('API body exceeds byte budget')
                    chunks.append(chunk)
            return decode_json(b''.join(chunks),max_bytes=96*1024*1024)
        except Exception as exc:
            raise ControlError('SOURCE_NOT_ALLOWED','GitHub API read failed; credential and response bodies omitted') from exc

    def close(self):self.client.close()


def dispatch_event(event_path:Path,site_path:Path):
    from ..core.config import load_site
    from ..core.rpc import rpc_call
    from ..sources.github_reader import GitHubReader
    site=load_site(site_path)
    api=GitHubApi(os.environ.get(site.settings.get('github_token_env','GITHUB_TOKEN'),''))
    try:
        repository=site.settings['github_repository']
        gateway=GitHubGateway(site,lambda n:api.get(f'/repos/{repository}/issues/{n}'),
            lambda call,context:rpc_call(site.root/'broker.sock',call,context=context),
            GitHubReader(api.get,site.repositories,site.limits['max_input_bytes']))
        return gateway.dispatch(decode_json(event_path.read_bytes()))
    finally:api.close()
