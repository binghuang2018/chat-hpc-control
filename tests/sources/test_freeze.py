import hashlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from chat_hpc_control.contracts.codec import parse_task
from chat_hpc_control.contracts.config import ExecutorConfig, SiteConfig
from chat_hpc_control.contracts.errors import ControlError


def source_api(name):
    try:
        return importlib.import_module("chat_hpc_control.sources." + name)
    except ModuleNotFoundError:
        pytest.fail("frozen source implementation is missing")


@pytest.fixture
def site(tmp_path):
    return SiteConfig("example-site", tmp_path / "site", {}, {}, ExecutorConfig("local", "example-local"),
                      limits={"max_input_bytes": 1024, "max_input_files": 10})


def archive(tmp_path, entries):
    path = tmp_path / "input.tar"
    with tarfile.open(path, "w") as out:
        for name, data, kind in entries:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            if kind == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "/etc/passwd"
                member.size = 0
            elif kind == "hardlink":
                member.type = tarfile.LNKTYPE
                member.linkname = "../outside"
                member.size = 0
            out.addfile(member, io.BytesIO(data))
    return path


@pytest.mark.parametrize("entries", [
    [("../outside", b"x", "file")], [("/absolute", b"x", "file")],
    [("job.py", b"x", "file"), ("job.py", b"y", "file")],
    [("café.py", b"x", "file"), ("cafe\u0301.py", b"x", "file")],
    [("job.py", b"", "symlink")], [("job.py", b"", "hardlink")],
])
def test_paths_are_rejected_before_copy(tmp_path, site, entries):
    cls = source_api("bundle").BundleStore
    store = cls(site)
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        store.import_tar(archive(tmp_path, entries))
    assert not (site.root / "bundles").exists()
    assert not (tmp_path / "outside").exists()


def test_bundle_roundtrip_and_digest(tmp_path, site, sample_task):
    store = source_api("bundle").BundleStore(site)
    bundle_id = store.import_tar(archive(tmp_path, [("job.py", b"print(1)\n", "file")]))
    sample_task["source"]["bundle_id"] = bundle_id
    resolved = source_api("base").SourceResolver().resolve(parse_task(json.dumps(sample_task).encode()), site)
    assert resolved.files == {"job.py": b"print(1)\n"}
    assert resolved.source_identity["bundle_id"] == bundle_id
    target = site.root / "bundles" / bundle_id / "files" / "job.py"
    target.chmod(0o600)
    target.write_bytes(b"tamper")
    with pytest.raises(ControlError, match="INPUT_CHANGED"):
        store.read(bundle_id)


def test_bundle_limit(tmp_path, site):
    cls = source_api("bundle").BundleStore
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        cls(site).import_tar(archive(tmp_path, [("job.py", b"x" * 1025, "file")]))


def test_branch_moves_and_blob_is_verified(tmp_path, site, sample_task):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    def git(*args):
        return subprocess.check_output(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                                        "-C", str(repo), *args]).decode().strip()
    (repo / "job.py").write_bytes(b"old\n")
    git("add", "job.py"); git("commit", "-m", "old")
    commit = git("rev-parse", "HEAD")
    site.repositories["https://github.com/example-lab/inputs"] = str(repo)
    sample_task["source"] = {"kind": "git", "repository": "https://github.com/example-lab/inputs",
                              "ref": "main", "files": ["job.py"]}
    resolved = source_api("base").SourceResolver().resolve(parse_task(json.dumps(sample_task).encode()), site)
    (repo / "job.py").write_bytes(b"new\n")
    git("add", "job.py"); git("commit", "-m", "new")
    assert resolved.task.source["ref"] == commit
    assert resolved.files["job.py"] == b"old\n"
    reader = source_api("git").GitCliReader(site.repositories)
    assert reader.read_blob(sample_task["source"]["repository"], commit, "job.py")[1] == b"old\n"
    limited = source_api("git").GitCliReader(site.repositories, max_bytes=2)
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        limited.read_blob(sample_task["source"]["repository"], commit, "job.py")


def test_blob_mismatch(site, sample_task):
    source_api("base")
    class CorruptReader:
        def resolve_ref(self, repository, ref):
            return "a" * 40
        def read_blob(self, repository, commit, path):
            return "b" * 40, b"wrong"
    site.repositories["https://github.com/example-lab/inputs"] = "/unused-local-mirror"
    sample_task["source"] = {"kind": "git", "repository": "https://github.com/example-lab/inputs",
                              "ref": "main", "files": ["job.py"]}
    with pytest.raises(ControlError, match="INPUT_CHANGED"):
        source_api("base").SourceResolver(CorruptReader()).resolve(parse_task(json.dumps(sample_task).encode()), site)


def test_git_ref_option_and_symlink_rejected(site, tmp_path):
    reader = source_api("git").GitCliReader({"allowed": str(tmp_path)})
    with pytest.raises(ControlError, match="SCHEMA_INVALID"):
        reader.resolve_ref("allowed", "--help")


@pytest.mark.parametrize('limits,expected_reads',[
    ({'max_input_files':1,'max_input_bytes':100},0),
    ({'max_input_files':10,'max_input_bytes':5},2),
])
def test_git_source_checks_count_upfront_and_bytes_incrementally(site,sample_task,limits,expected_reads):
    from dataclasses import replace
    calls=[]
    class Reader:
        def resolve_ref(self,*_):return 'a'*40
        def read_blob(self,repository,commit,path):
            calls.append(path);raw=b'1234'
            return hashlib.sha1(b'blob 4\0'+raw).hexdigest(),raw
    task={**sample_task,'source':{'kind':'git','repository':'example/repo','ref':'main','files':['job.py','b','c','d']}}
    config=replace(site,limits=limits,repositories={'example/repo':{}})
    with pytest.raises(ControlError,match='SCHEMA_INVALID'):
        source_api('base').SourceResolver(Reader()).resolve(parse_task(json.dumps(task).encode()),config)
    assert len(calls)==expected_reads
