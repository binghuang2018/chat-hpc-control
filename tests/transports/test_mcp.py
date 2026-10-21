import asyncio,hashlib,importlib,time
from dataclasses import replace
import pytest
from tests.transports.test_github import github_case
from chat_hpc_control.contracts.tools import ToolResponse
from chat_hpc_control.core.service import tool_definitions


def api():
    try:return importlib.import_module('chat_hpc_control.transports.mcp_server')
    except ModuleNotFoundError:pytest.fail('MCP server missing')


def test_exact_six_tools_and_scope_context(github_case):
    pytest.importorskip('mcp',reason='run in optional MCP SDK environment')
    from mcp import Client
    from chat_hpc_control.transports.mcp_auth import TokenAuthenticator
    from chat_hpc_control.core.auth import _context
    _,_,site=github_case
    contexts=[]
    class Service:
        def handle(self,call,context):
            contexts.append(context)
            return ToolResponse('test',True,{'observed_principal':context.principal})
    auth=TokenAuthenticator(site,[],local_context=_context('alice',site,transport='mcp'))
    server=api().create_mcp_server(Service(),auth)
    async def check():
        async with Client(server) as client:
            listed=await client.list_tools()
            tools=listed.tools if hasattr(listed,'tools') else listed
            assert {t.name for t in tools}=={t['name'] for t in tool_definitions()}
            for tool in tools:
                expected=next(t for t in tool_definitions() if t['name']==tool.name)
                assert tool.input_schema==expected['inputSchema']
                assert tool.annotations.read_only_hint==expected['readOnlyHint']
            result=await client.call_tool('get_task_status',{'site_id':site.site_id,'run_id':'test'})
            assert result.structured_content['ok']
            bad=await client.call_tool('get_task_status',{'site_id':site.site_id,'run_id':'test','principal':'mallory'})
            assert bad.structured_content['error']['code']=='SCHEMA_INVALID'
    asyncio.run(check())
    assert len(contexts)==1 and contexts[0].principal=='alice'


def test_unauthenticated_memory_call_denied(github_case):
    pytest.importorskip('mcp',reason='run in optional MCP SDK environment')
    from mcp import Client
    from chat_hpc_control.transports.mcp_auth import TokenAuthenticator
    _,_,site=github_case
    class Service:
        def handle(self,*args):raise AssertionError('unauthenticated dispatch')
    server=api().create_mcp_server(Service(),TokenAuthenticator(site,[]))
    async def check():
        async with Client(server) as client:
            result=await client.call_tool('list_capabilities',{'site_id':site.site_id})
            assert result.structured_content['error']['code']=='AUTH_DENIED'
    asyncio.run(check())


def test_http_auth_gate_and_duplicate_json(github_case):
    pytest.importorskip('mcp',reason='run in optional MCP SDK environment')
    from starlette.testclient import TestClient
    from chat_hpc_control.transports.mcp_auth import TokenAuthenticator
    _,_,site=github_case
    entries=[{'sha256':hashlib.sha256(b'synthetic').hexdigest(),'principal':'alice','site_id':site.site_id,
              'scopes':['tasks:read'],'expires_at':int(time.time())+60}]
    class Service:
        def handle(self,*args):raise AssertionError('invalid HTTP entered dispatch')
    server=api().create_mcp_server(Service(),TokenAuthenticator(site,entries))
    with TestClient(server.streamable_http_app(stateless_http=True)) as client:
        result=client.post('/mcp',content='{}')
        assert result.status_code==401
        result=client.post('/mcp',headers={'Authorization':'Bearer synthetic'},content='{"id":1,"id":2}')
        assert result.status_code==400


def test_http_passes_per_request_authenticated_context(github_case):
    pytest.importorskip('mcp',reason='run in optional MCP SDK environment')
    from starlette.testclient import TestClient
    from chat_hpc_control.transports.mcp_auth import TokenAuthenticator
    _,_,site=github_case
    entries=[{'sha256':hashlib.sha256(token.encode()).hexdigest(),'principal':who,'site_id':site.site_id,
              'scopes':['tasks:read'],'expires_at':int(time.time())+60}
             for token,who in [('synthetic-alice','alice'),('synthetic-maintainer','maintainer')]]
    contexts=[]
    class Service:
        def handle(self,call,context):
            contexts.append(context.principal)
            return ToolResponse('test',True,{'principal':context.principal})
    server=api().create_mcp_server(Service(),TokenAuthenticator(site,entries))
    with TestClient(server.streamable_http_app(stateless_http=True,json_response=True),base_url="http://127.0.0.1:8000") as client:
        for token,who in [('synthetic-alice','alice'),('synthetic-maintainer','maintainer')]:
            result=client.post('/mcp',headers={'Authorization':'Bearer '+token,
              'Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'tools/call',
              'params':{'name':'get_task_status','arguments':{'site_id':site.site_id,'run_id':'test'}}})
            assert result.status_code==200,result.text
            assert result.json()['result']['structuredContent']['data']['principal']==who,result.text
    assert contexts==['alice','maintainer']


def test_stateful_http_not_exposed_without_session_identity_binding(github_case):
    pytest.importorskip('mcp',reason='run in optional MCP SDK environment')
    from chat_hpc_control.transports.mcp_auth import TokenAuthenticator
    _,_,site=github_case
    entries=[{'sha256':hashlib.sha256(b'synthetic').hexdigest(),'principal':'alice','site_id':site.site_id,
              'scopes':['tasks:read'],'expires_at':int(time.time())+60}]
    server=api().create_mcp_server(None,TokenAuthenticator(site,entries))
    with pytest.raises(Exception):server.streamable_http_app(stateless_http=False)
