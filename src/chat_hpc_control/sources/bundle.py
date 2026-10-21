"""Administrator bundle staging with preflight validation and content hashes."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

from ..contracts.codec import decode_json
from ..contracts.config import SiteConfig
from ..contracts.errors import ControlError
from .base import checked_paths, check_limits


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
            content = path.read_bytes()
        except OSError as exc:
            raise ControlError("INPUT_CHANGED", "snapshot file unavailable") from exc
        if len(content) != rec["size"] or hashlib.sha256(content).hexdigest() != rec["sha256"]:
            raise ControlError("INPUT_CHANGED", "snapshot file digest changed")
        data[rec["path"]] = content
    return data


class BundleStore:
    def __init__(self, site: SiteConfig):
        self.site = site
        self.root = site.root / "bundles"

    def import_tar(self, source: Path) -> str:
        data = {}
        try:
            with tarfile.open(source, "r:*") as archive:
                members = archive.getmembers()
                if len(members) > self.site.limits.get("max_input_files", 1024):
                    raise ControlError("SCHEMA_INVALID", "too many archive members")
                names = checked_paths([m.name for m in members])
                if any(not m.isfile() for m in members):
                    raise ControlError("SCHEMA_INVALID", "archive must contain only regular files")
                if sum(m.size for m in members) > self.site.limits.get("max_input_bytes", 64 * 1024 * 1024):
                    raise ControlError("SCHEMA_INVALID", "archive exceeds input limit")
                for member in members:
                    with archive.extractfile(member) as stream:
                        data[member.name] = stream.read()
        except (tarfile.TarError, OSError) as exc:
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
