import socket
import pytest


def test_gemini_real_sdk_retries_are_disabled(monkeypatch):
    genai=pytest.importorskip('google.genai',reason='run in optional Google SDK environment')
    httpx=pytest.importorskip('httpx',reason='Google SDK HTTPX transport required')
    from chat_hpc_control.clients.gemini import create_adapter
    calls=[]
    def blocked(*args,**kwargs):raise AssertionError('real network is forbidden')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    monkeypatch.setattr(socket,'getaddrinfo',blocked)
    def respond(request):
        calls.append(request)
        return httpx.Response(500,json={'error':{'code':500,'message':'synthetic failure','status':'INTERNAL'}})
    original=genai.Client
    def configured(**kwargs):
        kwargs['http_options']={**kwargs['http_options'],'httpx_client':httpx.Client(transport=httpx.MockTransport(respond))}
        return original(**kwargs)
    monkeypatch.setattr(genai,'Client',configured)
    adapter=create_adapter(model='synthetic-never-requested-remotely').connect('synthetic-not-real')
    try:
        with pytest.raises(Exception):adapter.request('synthetic input')
        assert len(calls)==1,'SDK performed hidden extra API attempts'
    finally:adapter.client.close()
