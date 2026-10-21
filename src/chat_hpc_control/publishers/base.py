"""Verify collections and raw snapshot identities before exporting any bytes."""

from dataclasses import asdict
import hashlib
from pathlib import Path
from typing import Protocol
from ..contracts.errors import ControlError
from ..contracts.results import PublishReceipt,OutputSnapshot
from ..engines.parsers.common import read
from ..results.collections import read_collection,result_bytes
from ..worker.receipt import write_once


class Publisher(Protocol):
    def publish(self,collection):...
    def reconcile_publish(self,receipt):...


def payload(collection,snapshot_store=None,*,include_raw=True):
    try:
        documents=read_collection(collection)
        data={'collection/'+name:(collection.root/name).read_bytes() for name in documents}
        data['collection/collection.json']=(collection.root/'collection.json').read_bytes()
        if include_raw and documents['raw-manifest.json']['files']:
            if snapshot_store is None:raise ValueError('configured raw snapshot store is required')
            provenance=documents['provenance.json'];digest=provenance['snapshot_sha256']
            if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('snapshot identity')
            root=Path(snapshot_store)/digest
            snap=OutputSnapshot(root,documents['raw-manifest.json']['files'],provenance['manifest_sha256'],provenance['terminal'])
            identity={'files':snap.files,'terminal':snap.terminal,'manifest_sha256':snap.manifest_sha256}
            if hashlib.sha256(result_bytes(identity)).hexdigest()!=digest:raise ValueError('snapshot binding')
            for row in snap.files:data['raw/'+row['path']]=read(snap,row['path'],max_bytes=row['size'])
        return data
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise ControlError('RESULT_UNVERIFIED','collection or raw evidence could not be verified for publication') from exc


def inventory(data):
    return [{'path':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in sorted(data.items())]


def content_digest(data):return hashlib.sha256(result_bytes(inventory(data))).hexdigest()


def record_publication(site,receipt):
    if receipt.state not in {'PUBLISHED','PUBLISH_UNKNOWN','RENEWAL_REQUIRED'}:
        raise ControlError('SCHEMA_INVALID','unsupported publication receipt state')
    raw=result_bytes(asdict(receipt));digest=hashlib.sha256(raw).hexdigest()
    write_once(site.root/'publications'/receipt.collection_id/(digest+'.json'),raw)
    return digest
