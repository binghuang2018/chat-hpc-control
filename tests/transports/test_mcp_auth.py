import hashlib,importlib,time
from dataclasses import replace
import pytest
from tests.transports.test_github import github_case


def auth_api():
    try:return importlib.import_module('chat_hpc_control.transports.mcp_auth')
    except ModuleNotFoundError:pytest.fail('MCP authenticator missing')


def test_opaque_token_scope_expiry_and_site(github_case):
    _,_,site=github_case;module=auth_api()
    entries=[{'sha256':hashlib.sha256(b'synthetic-valid').hexdigest(),'principal':'alice','site_id':site.site_id,
              'scopes':['tasks:read'],'expires_at':int(time.time())+60}]
    auth=module.TokenAuthenticator(site,entries)
    ctx=auth.authenticate('synthetic-valid',site.site_id)
    assert ctx.principal=='alice' and ctx.scopes=={'tasks:read'}
    for token,target in [('unknown',site.site_id),('synthetic-valid','other')]:
        with pytest.raises(Exception):auth.authenticate(token,target)
    expired=module.TokenAuthenticator(site,[{**entries[0],'expires_at':0}])
    with pytest.raises(Exception):expired.authenticate('synthetic-valid',site.site_id)
    assert 'synthetic-valid' not in repr(auth.__dict__)


def test_http_requires_auth_and_tls_gateway(github_case):
    _,_,site=github_case;module=auth_api()
    with pytest.raises(Exception):module.validate_http_config(site,[])
    unsafe=replace(site,settings={**site.settings,'mcp_host':'0.0.0.0'})
    with pytest.raises(Exception):module.validate_http_config(unsafe,[{}])
