import json,os,sys
from pathlib import Path
import pytest
from chat_hpc_control.demo import run_demo
from chat_hpc_control.contracts.errors import ControlError


def test_resume_never_adopts_a_foreign_site_root(tmp_path,monkeypatch):
    root=tmp_path/'demo';root.mkdir()
    # Keep the Unix socket path short independently of host pytest tmp names.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='chc-guard-',dir='/tmp') as short:
        root=Path(short)
        (root/'demo-owner.json').write_text(json.dumps({'schema':'chat-hpc-control/demo-owner/v1','uid':os.getuid()}))
        template=Path(__file__).parents[2]/'examples/site.demo.toml.in'
        text=template.read_text()
        for key,value in {'@ROOT@':json.dumps(str(tmp_path/'foreign-state')),'@PYTHON@':json.dumps(sys.executable),
                          '@UID@':str(os.getuid()),'@CPUS@':'1'}.items():text=text.replace(key,value)
        (root/'site.toml').write_text(text)
        monkeypatch.setattr('chat_hpc_control.demo.sys.platform','linux')
        monkeypatch.setattr('chat_hpc_control.demo.platform.machine',lambda:'x86_64')
        monkeypatch.setattr('chat_hpc_control.demo.subprocess.Popen',lambda *a,**k:pytest.fail('foreign demo launched a broker'))
        with pytest.raises(ControlError,match='AUTH_DENIED'):run_demo(root,resume=True)
        assert not (tmp_path/'foreign-state').exists()
