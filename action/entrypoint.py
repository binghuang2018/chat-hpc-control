"""Use only an administrator-installed distribution, never execute QC input here."""
import os
from pathlib import Path
from chat_hpc_control.contracts.codec import encode_response
from chat_hpc_control.transports.github import dispatch_event

if __name__=='__main__':
    response=dispatch_event(Path(os.environ['GITHUB_EVENT_PATH']),Path(os.environ['CHC_SITE_CONFIG']))
    print(encode_response(response).decode())
    raise SystemExit(0 if response.ok else 2)
