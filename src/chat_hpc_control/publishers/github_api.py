"""Explicit control-gateway GitHub write credential; never used by the broker."""

import base64
import re
from urllib.parse import quote
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..sources.github_reader import GitHubReader


class GitHubWriteApi:
    def __init__(self,repository,token,*,client=None):
        if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not token:
            raise ControlError('AUTH_DENIED','explicit configured publication repository and write credential required')
        try:import httpx
        except ImportError as exc:raise ControlError('CAPABILITY_UNSUPPORTED','install chat-hpc-control[github] on the publication gateway') from exc
        self.repository=repository;self.base='/repos/'+repository
        self.client=client or httpx.Client(base_url='https://api.github.com',headers={'Authorization':'Bearer '+token,
            'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},timeout=20,follow_redirects=False)

    def _request(self,method,path,data=None,params=None):
        if not path.startswith(self.base+'/'):raise ControlError('SOURCE_NOT_ALLOWED','publication request escaped fixed repository')
        try:
            with self.client.stream(method,path,json=data,params=params) as response:
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>96*1024*1024:raise ValueError('response budget')
                    chunks.append(chunk)
            return decode_json(b''.join(chunks),max_bytes=96*1024*1024)
        except Exception as exc:raise ControlError('PUBLISH_UNKNOWN','GitHub write/readback outcome unavailable; preserve publication intent') from exc

    def get(self,path,params=None):return self._request('GET',path,params=params)
    def get_ref(self,branch):return self.get(self.base+'/git/ref/heads/'+quote(branch,safe=''))['object']['sha']

    def create_tree(self,base,files):
        tree=self.get(self.base+'/git/commits/'+base)['tree']['sha'];entries=[]
        for name,raw in sorted(files.items()):
            blob=self._request('POST',self.base+'/git/blobs',{'content':base64.b64encode(raw).decode(),'encoding':'base64'})
            entries.append({'path':name,'mode':'100644','type':'blob','sha':blob['sha']})
        return self._request('POST',self.base+'/git/trees',{'base_tree':tree,'tree':entries})['sha']

    def create_commit(self,base,tree,message):
        return self._request('POST',self.base+'/git/commits',{'message':message,'tree':tree,'parents':[base]})['sha']

    def update_ref(self,branch,commit,*,force):
        if force is not False:raise ControlError('AUTH_DENIED','force updates are not supported')
        return self._request('PATCH',self.base+'/git/refs/heads/'+quote(branch,safe=''),{'sha':commit,'force':False})

    def read_files(self,commit,prefix):
        repository='https://github.com/'+self.repository
        reader=GitHubReader(self.get,{repository});tree=self.get(self.base+'/git/trees/'+commit,{'recursive':'1'})
        if tree.get('truncated') is not False:raise ControlError('PUBLISH_UNKNOWN','truncated publication tree')
        reader.trees[(repository,commit)]=tree['tree']
        names=[row['path'] for row in tree['tree'] if row['path'].startswith(prefix+'/') and row['type']!='tree']
        return {name[len(prefix)+1:]:reader.read_blob(repository,commit,name)[1] for name in names}

    def is_ancestor(self,base,head):
        data=self.get(self.base+'/compare/'+base+'...'+head)
        return data.get('status') in {'identical','ahead'}

    def close(self):self.client.close()
