"""Credential-free immutable Git snapshots shared by a trusted local gateway."""

import hashlib
from dataclasses import replace
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..core.manifest import canonical_bytes
from ..worker.receipt import write_once
from .base import SourceResolver
from .bundle import file_records,read_verified


def cache_root(site,repository,commit):
    import re
    if repository not in site.repositories or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',commit):
        raise ControlError('SOURCE_NOT_ALLOWED','Git cache identity is not approved')
    return site.root/'git-cache'/hashlib.sha256(repository.encode()).hexdigest()/commit


def stage_task(task,site,reader):
    resolved=SourceResolver(reader).resolve(task,site)
    source=resolved.source_identity;root=cache_root(site,source['repository'],source['commit'])
    # Each exact file set has a separate immutable receipt under the commit.
    rows=file_records(resolved.files)
    identity={**source,'files':rows}
    digest=hashlib.sha256(canonical_bytes(identity)).hexdigest()
    for name,raw in resolved.files.items():write_once(root/'files'/name,raw)
    write_once(root/'sets'/(digest+'.json'),canonical_bytes(identity))
    return resolved.task


class StagedGitReader:
    def __init__(self,site,fallback):self.site,self.fallback=site,fallback

    def resolve_ref(self,repository,ref):
        import re
        if re.fullmatch('[0-9a-f]{40}',ref) and cache_root(self.site,repository,ref).exists():return ref
        return self.fallback.resolve_ref(repository,ref)

    def read_blob(self,repository,commit,path):
        root=cache_root(self.site,repository,commit)
        if not root.exists():return self.fallback.read_blob(repository,commit,path)
        for record_path in sorted((root/'sets').glob('*.json')):
            raw=record_path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=record_path.stem:raise ControlError('INPUT_CHANGED','Git cache receipt changed')
            manifest=decode_json(raw)
            if manifest['repository']!=repository or manifest['commit']!=commit:raise ControlError('INPUT_CHANGED','Git cache identity changed')
            row=next((r for r in manifest['files'] if r['path']==path),None)
            if row:
                target=root/'files'/path
                if target.is_symlink() or not target.resolve().is_relative_to((root/'files').resolve()):
                    raise ControlError('INPUT_CHANGED','Git cache path changed')
                content=target.read_bytes()
                if len(content)!=row['size'] or hashlib.sha256(content).hexdigest()!=row['sha256']:
                    raise ControlError('INPUT_CHANGED','Git cache blob changed')
                return manifest['blobs'][path],content
        raise ControlError('SOURCE_NOT_ALLOWED','Git path has not been staged by the gateway')
