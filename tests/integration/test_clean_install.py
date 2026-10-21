import json,os,platform,subprocess,sys,tempfile
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[2]
pytestmark=[pytest.mark.linux,pytest.mark.skipif(sys.platform!='linux' or platform.machine()!='x86_64',reason='clean Linux x86_64 native demo required')]


def test_quickstart_clean_home_and_resume(tmp_path):
    wheels=tmp_path/'wheels';wheels.mkdir()
    for project in (ROOT,ROOT/'examples/plugins/demo-engine'):
        subprocess.run([sys.executable,'-m','build','--wheel','--no-isolation','--outdir',str(wheels),str(project)],check=True,capture_output=True,text=True)
    envroot=tmp_path/'env'
    subprocess.run(['uv','venv','--python',sys.executable,str(envroot)],check=True,capture_output=True)
    subprocess.run(['uv','pip','install','--python',str(envroot/'bin/python'),*map(str,wheels.glob('*.whl'))],check=True,capture_output=True)
    home=tmp_path/'clean-home';home.mkdir()
    environment={'PATH':os.defpath,'HOME':str(home),'LANG':'C.UTF-8'}
    with tempfile.TemporaryDirectory(prefix='chc-clean-') as root:
        directory=Path(root)/'demo'
        argv=[str(envroot/'bin/python'),'-I','-m','chat_hpc_control.cli','demo','--root',str(directory)]
        first=subprocess.run(argv,cwd=home,env=environment,text=True,capture_output=True,timeout=180)
        assert first.returncode==0,first.stdout+first.stderr
        one=json.loads(first.stdout)['data']
        assert one['execution_state']=='COMPLETED' and one['collection_id'] and one['synthetic']
        assert one['data_ready'] is False
        second=subprocess.run([*argv,'--resume'],cwd=home,env=environment,text=True,capture_output=True,timeout=180)
        assert second.returncode==0,second.stdout+second.stderr
        two=json.loads(second.stdout)['data']
        assert one['run_id']==two['run_id'] and one['collection_id']==two['collection_id']
        assert not (home/'.ssh').exists()
