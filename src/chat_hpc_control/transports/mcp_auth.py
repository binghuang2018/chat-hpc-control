"""Private opaque bearer authentication, not an OAuth authorization server."""

from dataclasses import replace
import hashlib
import hmac
import re
import time
from ..contracts.errors import ControlError
from ..core.auth import _context


class TokenAuthenticator:
    def __init__(self,site,entries,*,local_context=None):
        self.site,self.entries,self.local_context=site,[],local_context
        seen=set()
        for entry in entries:
            if (set(entry)!={'sha256','principal','site_id','scopes','expires_at'}
                    or not re.fullmatch('[0-9a-f]{64}',entry['sha256']) or entry['sha256'] in seen
                    or entry['site_id']!=site.site_id or type(entry['expires_at'])!=int
                    or not isinstance(entry['scopes'],list) or not all(isinstance(s,str) for s in entry['scopes'])):
                raise ControlError('SCHEMA_INVALID','invalid private bearer digest configuration')
            _context(entry['principal'],site,entry['scopes'],transport='mcp')
            seen.add(entry['sha256']);self.entries.append(dict(entry))
        if local_context is not None:
            expected=_context(local_context.principal,site,local_context.scopes,transport='mcp')
            if local_context.site_id!=site.site_id:raise ControlError('AUTH_DENIED','local MCP site mismatch')
            self.local_context=expected

    def authenticate(self,token,site_id):
        if not isinstance(token,str) or not 0<len(token)<=4096 or site_id!=self.site.site_id:
            raise ControlError('AUTH_DENIED','bearer authentication failed')
        digest=hashlib.sha256(token.encode()).hexdigest();match=None
        for entry in self.entries:
            if hmac.compare_digest(entry['sha256'],digest):match=entry
        if match is None or match['expires_at']<=time.time():
            raise ControlError('AUTH_DENIED','bearer authentication failed')
        return _context(match['principal'],self.site,match['scopes'],transport='mcp')


def validate_http_config(site,entries):
    host=site.settings.get('mcp_host','127.0.0.1')
    external=site.settings.get('mcp_external_url')
    if not entries or host not in {'127.0.0.1','::1','localhost'}:
        raise ControlError('AUTH_DENIED','MCP HTTP requires bearer digests and a loopback bind')
    if external and (not external.startswith('https://') or site.settings.get('mcp_tls_gateway') is not True):
        raise ControlError('AUTH_DENIED','external MCP access requires an explicit HTTPS gateway')
    return host
