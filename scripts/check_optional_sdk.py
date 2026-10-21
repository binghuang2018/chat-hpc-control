"""Offline SDK/import/adapter check; creates clients but performs zero requests."""
import argparse
from importlib import import_module,metadata
import json
import socket
import sys


def main():
    parser=argparse.ArgumentParser();parser.add_argument('provider',choices=['openai','anthropic','gemini'])
    name=parser.parse_args().provider
    def no_connect(*args,**kwargs):raise AssertionError('network use forbidden during SDK import check')
    socket.socket.connect=no_connect
    module=import_module('chat_hpc_control.clients.'+name)
    assert not {'openai','anthropic','google.genai'}&sys.modules.keys()
    adapter=module.create_adapter(model='synthetic-unrequested-model').connect('synthetic-not-a-real-key')
    assert len(adapter.tool_definitions())==6
    distribution={'gemini':'google-genai'}.get(name,name)
    print(json.dumps({'provider':name,'version':metadata.version(distribution),'sdk_import':'PASS','api_calls':0}))
    adapter.client.close()


if __name__=='__main__':main()
