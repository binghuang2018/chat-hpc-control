import pytest


def test_archive_surrogate_path_is_a_controlled_schema_error():
    from chat_hpc_control.sources.base import checked_paths
    from chat_hpc_control.contracts.errors import ControlError
    with pytest.raises(ControlError,match='SCHEMA_INVALID'):checked_paths(['invalid-\ud800'])


def test_read_limited_never_uses_an_unbounded_file_read(tmp_path,monkeypatch):
    from chat_hpc_control.sources.base import read_limited
    from chat_hpc_control.contracts.errors import ControlError
    from pathlib import Path
    path=tmp_path/'output';path.write_bytes(b'0123456789')
    monkeypatch.setattr(Path,'read_bytes',lambda self:pytest.fail('unbounded read_bytes used'))
    with pytest.raises(ControlError):read_limited(path,3)
    assert read_limited(path,10)==b'0123456789'


def test_read_limited_rejects_a_fifo_without_waiting(tmp_path):
    import os,subprocess,sys
    path=tmp_path/'fifo';os.mkfifo(path)
    code='''from pathlib import Path
from chat_hpc_control.sources.base import read_limited
from chat_hpc_control.contracts.errors import ControlError
try:read_limited(Path(%r),10)
except ControlError:print('refused')
else:raise AssertionError('special file accepted')
''' % str(path)
    try:result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=2)
    except subprocess.TimeoutExpired:pytest.fail('bounded file reader blocked on a FIFO')
    assert result.returncode==0 and 'refused' in result.stdout,result.stderr


def test_bundle_member_limit_is_checked_without_loading_all_headers(tmp_path,monkeypatch):
    import io,tarfile
    from chat_hpc_control.contracts.config import SiteConfig,ExecutorConfig
    from chat_hpc_control.contracts.errors import ControlError
    from chat_hpc_control.sources.bundle import BundleStore
    archive=tmp_path/'many.tar'
    with tarfile.open(archive,'w') as out:
        for i in range(3):out.addfile(tarfile.TarInfo(f'job{i}.py'),io.BytesIO())
    monkeypatch.setattr(tarfile.TarFile,'getmembers',lambda self:pytest.fail('unbounded tar header inventory'))
    site=SiteConfig('example',tmp_path/'site',{}, {},ExecutorConfig('local','example'),limits={'max_input_files':2,'max_input_bytes':32})
    with pytest.raises(ControlError,match='SCHEMA_INVALID'):BundleStore(site).import_tar(archive)
    assert not site.root.exists()
