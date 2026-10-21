"""Idempotent immutable directory export for operator-selected local targets."""

import hashlib
from pathlib import Path
from ..contracts.codec import decode_json
from ..contracts.errors import ControlError
from ..contracts.results import PublishReceipt
from ..results.collections import result_bytes
from ..worker.receipt import write_once
from .base import payload,inventory,content_digest


class DirectoryPublisher:
    def __init__(self,target_root,*,snapshot_store=None):
        self.root=Path(target_root);self.snapshot_store=snapshot_store
        if not self.root.is_absolute() or self.root.is_symlink():raise ControlError('SCHEMA_INVALID','explicit absolute publication directory is required')

    def publish(self,collection):
        data=payload(collection,self.snapshot_store);digest=content_digest(data)
        target=self.root/collection.collection_id
        if target.is_symlink() or target.exists() and any(p.is_symlink() for p in target.rglob("*")):
            raise ControlError("RESULT_UNVERIFIED", "existing export contains a symbolic link")
        for name,raw in data.items():write_once(target/name,raw);(target/name).chmod(0o400)
        write_once(target/'publication.json',result_bytes({'collection_id':collection.collection_id,'files':inventory(data)}))
        return PublishReceipt(collection.collection_id,'directory:'+str(self.root),'PUBLISHED',
                              {'content_sha256':digest,'path':str(target),'availability':'LOCAL'})

    def reconcile_publish(self,receipt):
        try:
            if receipt.target != "directory:"+str(self.root):raise ValueError("publication target mismatch")
            target=self.root/receipt.collection_id
            manifest=decode_json((target/'publication.json').read_bytes())
            from ..sources.bundle import checked_paths
            checked_paths([r['path'] for r in manifest['files']])
            if any(p.is_symlink() for p in target.rglob('*')):raise ValueError('linked export')
            actual={p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
            if actual!={r['path'] for r in manifest['files']}|{'publication.json'}:raise ValueError('export inventory changed')
            data={r['path']:(target/r['path']).read_bytes() for r in manifest['files']}
            if (manifest['collection_id']!=receipt.collection_id or inventory(data)!=manifest['files']
                    or content_digest(data)!=receipt.identity['content_sha256']):raise ValueError('export changed')
            return receipt
        except (OSError,ValueError,KeyError):
            return PublishReceipt(receipt.collection_id,receipt.target,'PUBLISH_UNKNOWN',receipt.identity)
