import importlib.util,json,subprocess,sys,tarfile,zipfile
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]


def release_tool():
    spec=importlib.util.spec_from_file_location('release_manifest',ROOT/'tools/release_manifest.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_release_evidence(tmp_path):
    dist=tmp_path/'dist';dist.mkdir();(dist/'synthetic.whl').write_bytes(b'synthetic')
    evidence=tmp_path/'evidence';evidence.mkdir()
    (evidence/'fake.json').write_text(json.dumps({'name':'invented','status':'PASS'}))
    with pytest.raises(ValueError):release_tool().build_release_manifest(dist,evidence)


def test_ci_no_live_default():
    for name in ('ci.yml','release-candidate.yml'):
        text=(ROOT/'.github/workflows'/name).read_text()
        assert 'secrets.' not in text and 'self-hosted' not in text and 'pypa/gh-action-pypi-publish' not in text
        assert 'not qc_live and not provider_live and not github_live' in text
    for name in ('LICENSE','CHANGELOG.md','CONTRIBUTING.md','SECURITY.md','docs/v0.1-acceptance.md'):
        assert (ROOT/name).is_file()


@pytest.fixture(scope='module')
def distributions(tmp_path_factory):
    directory=tmp_path_factory.mktemp('release-packages')
    subprocess.run([sys.executable,'-m','build','--no-isolation','--outdir',str(directory),str(ROOT)],check=True,capture_output=True,text=True)
    return directory


def test_wheel_contents(distributions):
    with zipfile.ZipFile(next(distributions.glob('*.whl'))) as archive:
        names=archive.namelist()
        assert any('/schemas/task-v1.json' in n for n in names)
        assert any('licenses/LICENSE' in n for n in names)
        assert all(not any(part in n.split('/') for part in ('.git','runtime','.superpowers','tests')) for n in names)
        for n in names:
            raw=archive.read(n)
            assert b'/'+b'Users/' not in raw and b'/home/'+b'ghrunner' not in raw


def test_sdist_rebuild(distributions,tmp_path):
    with tarfile.open(next(distributions.glob('*.tar.gz'))) as archive:
        # Test only our just-built archive; all paths still require one top root.
        names=archive.getnames();assert all(not n.startswith('/') and '..' not in n.split('/') for n in names)
        allowed={'src','tests','examples','docs','tools','scripts','constraints','.github','action.yml','pyproject.toml','README.md','README.zh-CN.md','LICENSE','CHANGELOG.md','CONTRIBUTING.md','SECURITY.md','PKG-INFO','.gitignore'}
        assert all(n.split('/')[1] in allowed for n in names), 'sdist contains undeclared development/private files'
        archive.extractall(tmp_path,filter='data')
    project=next(p for p in tmp_path.iterdir() if p.is_dir())
    out=tmp_path/'rebuilt'
    subprocess.run([sys.executable,'-m','build','--wheel','--no-isolation','--outdir',str(out),str(project)],check=True,capture_output=True,text=True)
    environment=tmp_path/'env'
    subprocess.run(['uv','venv','--python',sys.executable,str(environment)],check=True,capture_output=True)
    python=environment/'bin/python'
    subprocess.run(['uv','pip','install','--python',str(python),str(next(out.glob('*.whl')))],check=True,capture_output=True)
    result=subprocess.run([str(python),'-I','-c','import chat_hpc_control; from importlib.metadata import version; print(version("chat-hpc-control"))'],cwd=tmp_path,capture_output=True,text=True,check=True)
    assert result.stdout.strip()=='0.1.0'


def test_core_without_extras(tmp_path):
    script='''
import sys
from chat_hpc_control.clients.openai import create_adapter
from chat_hpc_control.contracts.errors import ControlError
sys.modules['openai']=None
try: create_adapter(model='synthetic').connect('synthetic')
except ControlError as exc: assert exc.code=='CAPABILITY_UNSUPPORTED'
else: raise AssertionError('missing SDK was silently accepted')
'''
    subprocess.run([sys.executable,'-c',script],check=True,capture_output=True,text=True)


def test_distribution_metadata_valid(distributions):
    result=subprocess.run([sys.executable,'-m','twine','check','--strict',*map(str,distributions.iterdir())],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
