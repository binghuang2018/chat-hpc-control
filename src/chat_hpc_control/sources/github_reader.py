"""GitHub gateway reads fixed commit/tree/blob identities, never download URLs."""

import base64
import hashlib
import re
from urllib.parse import quote
from ..contracts.errors import ControlError
from .base import checked_paths


class GitHubReader:
    def __init__(self,get,allowed_repositories,max_bytes=67108864):
        self.get,self.allowed,self.max_bytes=get,set(allowed_repositories),max_bytes
        self.refs,self.trees={},{}

    def _repo(self,repository):
        if repository not in self.allowed or not re.fullmatch(r'https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
            raise ControlError('SOURCE_NOT_ALLOWED','GitHub repository is not approved')
        return '/repos/'+repository.removeprefix('https://github.com/')

    def resolve_ref(self,repository,ref):
        base=self._repo(repository)
        if re.fullmatch('[0-9a-f]{40}',ref):return ref
        if not isinstance(ref,str) or not ref or len(ref)>512 or any(ord(c)<32 for c in ref):
            raise ControlError('SCHEMA_INVALID','invalid Git ref')
        key=(repository,ref)
        if key not in self.refs:
            commit=self.get(base+'/commits/'+quote(ref,safe=''))['sha']
            if not re.fullmatch('[0-9a-f]{40}',commit):raise ControlError('INPUT_CHANGED','invalid Git commit identity')
            self.refs[key]=commit
        return self.refs[key]

    def read_blob(self,repository,commit,path):
        base=self._repo(repository);checked_paths([path])
        if not re.fullmatch('[0-9a-f]{40}',commit):raise ControlError('INPUT_CHANGED','blob read requires fixed commit')
        key=(repository,commit)
        if key not in self.trees:
            tree=self.get(base+'/git/trees/'+commit,{'recursive':'1'})
            if tree.get('truncated') is not False:raise ControlError('SOURCE_NOT_ALLOWED','truncated Git tree cannot prove file mode')
            self.trees[key]=tree['tree']
        matches=[r for r in self.trees[key] if r['path']==path]
        if len(matches)!=1 or matches[0].get('mode') not in {'100644','100755'} or matches[0].get('type')!='blob':
            raise ControlError('SOURCE_NOT_ALLOWED','Git path is not one regular blob')
        row=matches[0]
        if type(row.get('size'))!=int or not 0<=row['size']<=self.max_bytes:raise ControlError('SCHEMA_INVALID','Git blob exceeds byte budget')
        blob=self.get(base+'/git/blobs/'+row['sha'])
        if blob.get('encoding')!='base64' or blob.get('sha')!=row['sha'] or blob.get('size')!=row['size']:
            raise ControlError('INPUT_CHANGED','Git blob metadata differs')
        raw=base64.b64decode(''.join(blob['content'].split()),validate=True)
        digest=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
        if digest!=row['sha'] or len(raw)!=row['size']:raise ControlError('INPUT_CHANGED','Git blob content differs')
        return digest,raw
