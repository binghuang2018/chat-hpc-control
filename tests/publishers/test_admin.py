import os
from pathlib import Path
import pytest
from chat_hpc_control.contracts.config import SiteConfig,ExecutorConfig
from chat_hpc_control.contracts.tools import ToolResponse
from chat_hpc_control.publishers.admin import operate


def test_publication_requires_separate_operator_scope(publish_case,monkeypatch):
    ref,snapshots,root=publish_case
    site=SiteConfig('example',root,{'alice':{'scopes':['results:read']}},{},ExecutorConfig('local','example'),local_principals={os.getuid():'alice'})
    monkeypatch.setattr('chat_hpc_control.publishers.admin.rpc_call',lambda *a,**k:pytest.fail('denied publisher called RPC'))
    with pytest.raises(Exception,match='AUTH_DENIED'):
        operate(site,operation='publish',target='missing',collection_root=ref.root)


def test_allowlisted_operator_directory_records_readable_receipt(publish_case,monkeypatch):
    ref,snapshots,root=publish_case
    site=SiteConfig('example',root,{'alice':{'scopes':['results:read','results:publish']}},{},ExecutorConfig('local','example'),
        local_principals={os.getuid():'alice'},settings={'publish_targets':{'local':{'kind':'directory','path':str(root/'export')}}})
    monkeypatch.setattr('chat_hpc_control.publishers.admin.rpc_call',lambda *a,**k:ToolResponse('r',True,{'collection_id':ref.collection_id}))
    result=operate(site,operation='publish',target='local',collection_root=ref.root)
    assert result['state']=='PUBLISHED'
    assert len(list((root/'publications'/ref.collection_id).glob('*.json')))==1
