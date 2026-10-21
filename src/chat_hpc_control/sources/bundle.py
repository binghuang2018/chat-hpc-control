"""Administrator bundle staging with preflight validation and content hashes."""

import hashlib
import bz2
import gzip
import lzma
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

from ..contracts.codec import decode_json
from ..contracts.config import SiteConfig
from ..contracts.errors import ControlError
from .base import checked_paths, check_limits, read_limited


def file_records(data: dict[str, bytes]) -> list[dict]:
    return [{"path": p, "size": len(data[p]), "sha256": hashlib.sha256(data[p]).hexdigest()}
            for p in sorted(data)]


def read_verified(root: Path, records: list[dict]) -> dict[str, bytes]:
    expected = checked_paths([r["path"] for r in records])
    if root.is_symlink() or any(p.is_symlink() for p in root.rglob("*")):
        raise ControlError("INPUT_CHANGED", "snapshot contains a symbolic link")
    actual = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    if actual != expected:
        raise ControlError("INPUT_CHANGED", "snapshot file inventory changed")
    data = {}
    for rec in records:
        path = root / rec["path"]
        try:
            content = read_limited(path, rec["size"], code="INPUT_CHANGED")
        except OSError as exc:
            raise ControlError("INPUT_CHANGED", "snapshot file unavailable") from exc
        if len(content) != rec["size"] or hashlib.sha256(content).hexdigest() != rec["sha256"]:
            raise ControlError("INPUT_CHANGED", "snapshot file digest changed")
        data[rec["path"]] = content
    return data


class _ArchiveBudget:
    def __init__(self,stream,limit):self.stream,self.limit,self.used=stream,limit,0
    def read(self,size=-1):
        allowed=self.limit-self.used+1
        raw=self.stream.read(min(size,allowed) if size>=0 else allowed)
        self.used+=len(raw)
        if self.used>self.limit:raise ControlError('SCHEMA_INVALID','archive decompression exceeds its bounded container budget')
        return raw


class BundleStore:
    def __init__(self, site: SiteConfig):
        self.site = site
        self.root = site.root / "bundles"

    def import_tar(self, source: Path) -> str:
        data = {}
        try:
            with ExitStack() as stack:
                raw=stack.enter_context(source.open('rb'));magic=raw.read(6);raw.seek(0)
                decoded=raw
                if magic.startswith(b'\x1f\x8b'):decoded=stack.enter_context(gzip.GzipFile(fileobj=raw))
                elif magic.startswith(b'BZh'):decoded=stack.enter_context(bz2.BZ2File(raw))
                elif magic.startswith(b'\xfd7zXZ\x00'):decoded=stack.enter_context(lzma.LZMAFile(raw))
                max_files=self.site.limits.get('max_input_files',1024)
                max_bytes=self.site.limits.get('max_input_bytes',64*1024*1024)
                bounded=_ArchiveBudget(decoded,max_bytes+16384*max_files+10240)
                archive=stack.enter_context(tarfile.open(fileobj=bounded,mode='r|'))
                names=[];total=0
                for member in archive:
                    if len(names)>=max_files:raise ControlError('SCHEMA_INVALID','too many archive members')
                    if not member.isfile():raise ControlError('SCHEMA_INVALID','archive must contain only regular files')
                    names.append(member.name);checked_paths(names)
                    total+=member.size
                    if total>max_bytes:raise ControlError('SCHEMA_INVALID','archive exceeds input limit')
                    with archive.extractfile(member) as stream:
                        content=stream.read(member.size+1)
                    if len(content)!=member.size:raise ControlError('SCHEMA_INVALID','archive member was truncated')
                    data[member.name]=content
                names=checked_paths(names)
        except (tarfile.TarError, OSError, EOFError, lzma.LZMAError) as exc:
            raise ControlError("SCHEMA_INVALID", "unreadable bundle archive") from exc
        check_limits(data, self.site)
        from ..core.manifest import canonical_bytes
        manifest = {"schema": "chat-hpc-control/bundle/v1", "files": file_records(data)}
        encoded = canonical_bytes(manifest)
        bundle_id = hashlib.sha256(encoded).hexdigest()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.root / bundle_id
        if target.exists():
            self.read(bundle_id)
            return bundle_id
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=self.root))
        try:
            for name in names:
                path = stage / "files" / name
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                path.write_bytes(data[name])
                path.chmod(0o400)
            (stage / "manifest.json").write_bytes(encoded)
            (stage / "manifest.json").chmod(0o400)
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return bundle_id

    def read(self, bundle_id: str) -> dict[str, bytes]:
        import re
        if not re.fullmatch(r"[0-9a-f]{64}", bundle_id):
            raise ControlError("SOURCE_NOT_ALLOWED", "bundle ID must be a content digest")
        root = self.root / bundle_id
        try:
            raw = (root / "manifest.json").read_bytes()
        except OSError as exc:
            raise ControlError("SOURCE_NOT_ALLOWED", "registered bundle is unavailable") from exc
        if hashlib.sha256(raw).hexdigest() != bundle_id or root.is_symlink():
            raise ControlError("INPUT_CHANGED", "bundle manifest changed")
        manifest = decode_json(raw)
        return read_verified(root / "files", manifest["files"])
