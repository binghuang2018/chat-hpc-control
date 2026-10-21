"""Shared parser identity and bounded immutable snapshot reads."""

import hashlib
from pathlib import Path
from ...contracts.codec import decode_json
from ...contracts.results import ParseReport
from ...sources.base import checked_paths


def identity(profile):
    root = Path(__file__).parent
    code = b''.join(p.name.encode()+p.read_bytes() for p in sorted(root.glob('*.py')))
    return {'profile':profile,'version':'1','code_sha256':hashlib.sha256(code).hexdigest(),
            'geometry_tolerance_bohr':'0.00001','angstrom_per_bohr':'0.529177210903'}


def read(snapshot,name):
    checked_paths([name])
    path=snapshot.root/name
    record=next((r for r in snapshot.files if r['path']==name),None)
    if record is None or path.is_symlink() or not path.resolve().is_relative_to(snapshot.root.resolve()):
        raise ValueError('file absent from immutable inventory')
    if path.stat().st_size>64*1024*1024 or path.stat().st_size!=record['size']:
        raise ValueError('file size differs from inventory')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=record['sha256']:
        raise ValueError('file hash differs from inventory')
    return raw


def options(snapshot):
    return decode_json(read(snapshot,'task-manifest.json'))['task']['engine_options']


def report(profile,records=None,issues=None,supported=True):
    return ParseReport(profile,identity(profile),records or [],issues or [],supported)


def failure(profile,code='PROFILE_UNVERIFIED',severity='unverified'):
    return report(profile,issues=[{'code':code,'severity':severity}],supported=False)
