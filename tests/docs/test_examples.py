from pathlib import Path
import json,os,subprocess,sys
import pytest
from chat_hpc_control.contracts.codec import parse_task
from chat_hpc_control.core.config import load_site
ROOT=Path(__file__).parents[2]


def test_examples_and_site_template(tmp_path):
    examples=list((ROOT/'examples/tasks').glob('*/task.json'))
    assert examples,'public task example is missing'
    for path in examples:assert parse_task(path.read_bytes()).resources.walltime_seconds is None
    template=ROOT/'examples/site.demo.toml.in'
    assert template.is_file(),'new-site configuration template is missing'
    text=template.read_text()
    for key,value in {'@ROOT@':json.dumps(str(tmp_path/'state')),'@PYTHON@':json.dumps(sys.executable),'@UID@':str(os.getuid()),'@CPUS@':'2'}.items():text=text.replace(key,value)
    config=tmp_path/'site.toml';config.write_text(text)
    site=load_site(config)
    assert site.site_id=='example-demo' and site.executor.kind=='local'
    assert not site.repositories


def test_documented_capabilities_are_evidence_qualified():
    expected=['quickstart.md','quickstart.zh-CN.md','plugin-guide.md','site-guide.md','results-guide.md','compatibility.md']
    for name in expected:assert (ROOT/'docs'/name).is_file(),name+' is missing'
    guide=(ROOT/'docs/compatibility.md').read_text()
    for term in ('Linux x86_64','macOS','RHF','advisory','NOT_EVALUATED','not exercised'):
        assert term in guide,term
    assert 'design-only' not in (ROOT/'README.md').read_text().lower()


def test_pytest_does_not_import_frozen_science_inputs():
    fixture=ROOT/'examples/tasks/test_frozen.py'
    assert fixture.is_file(),'test-discovery tripwire is missing'
    result=subprocess.run([sys.executable,'-m','pytest','--collect-only','-q'],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr+result.stdout
    assert 'examples/tasks/test_frozen.py' not in result.stdout
