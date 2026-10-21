"""Explicitly configured control-gateway client. Running this may incur API charges."""
import argparse
from importlib import import_module
import json
import os
from pathlib import Path
from chat_hpc_control.clients.session import ClientSessionStore
from chat_hpc_control.clients.loop import run_turn
from chat_hpc_control.contracts.auth import PeerIdentity
from chat_hpc_control.core.auth import context_from_peer
from chat_hpc_control.core.config import load_site
from chat_hpc_control.core.rpc import rpc_call


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',required=True,choices=['openai','anthropic','gemini'])
    parser.add_argument('--model',required=True);parser.add_argument('--api-key-env',required=True)
    parser.add_argument('--site',type=Path,required=True);parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--request-id',required=True);parser.add_argument('--prompt',required=True)
    parser.add_argument('--rerun-of');parser.add_argument('--max-rounds',type=int,default=4)
    parser.add_argument('--max-calls',type=int,default=16);parser.add_argument('--max-output-tokens',type=int,default=2048)
    args=parser.parse_args();site=load_site(args.site)
    context=context_from_peer(PeerIdentity(os.getuid(),os.getgid(),os.getpid()),{},site)
    adapter=import_module('chat_hpc_control.clients.'+args.provider).create_adapter(
        model=args.model,max_output_tokens=args.max_output_tokens).connect(os.environ.get(args.api_key_env,''))
    session=ClientSessionStore.open(args.session)
    try:
        session.bind_identity(site.site_id,context.principal)
        session.begin_request(args.request_id,args.prompt,rerun_of=args.rerun_of)
        result=run_turn(adapter,session,args.prompt,lambda call:rpc_call(site.root/'broker.sock',call),
                        max_rounds=args.max_rounds,max_calls=args.max_calls)
        print(json.dumps(result,allow_nan=False))
    finally:
        session.close();adapter.client.close()


if __name__=='__main__':main()
