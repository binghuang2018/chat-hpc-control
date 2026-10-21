import json
import pytest


def test_real_httpx_serializer_uses_fixed_repository_and_never_forces():
    httpx=pytest.importorskip('httpx',reason='run serializer test in optional HTTPX/MCP environment')
    from chat_hpc_control.publishers.github_api import GitHubWriteApi
    calls=[]
    def respond(request):
        assert request.url.host=='api.github.com'
        assert request.url.path.startswith('/repos/example/results/')
        calls.append((request.method,request.url.path,json.loads(request.content) if request.content else None))
        if request.method=='PATCH':
            assert json.loads(request.content)=={'sha':'c'*40,'force':False}
            return httpx.Response(200,json={'object':{'sha':'c'*40}})
        if '/git/ref/' in request.url.path:return httpx.Response(200,json={'object':{'sha':'a'*40}})
        if '/git/commits/' in request.url.path:return httpx.Response(200,json={'tree':{'sha':'b'*40}})
        return httpx.Response(201,json={'sha':'c'*40})
    with httpx.Client(base_url='https://api.github.com',transport=httpx.MockTransport(respond)) as client:
        api=GitHubWriteApi('example/results','synthetic-not-real',client=client)
        base=api.get_ref('results')
        tree=api.create_tree(base,{'results/example/summary.json':b'{}'})
        commit=api.create_commit(base,tree,'synthetic')
        api.update_ref('results',commit,force=False)
        with pytest.raises(Exception):api.update_ref('results',commit,force=True)
    assert 'synthetic-not-real' not in json.dumps(calls)
