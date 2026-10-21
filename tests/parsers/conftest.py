import hashlib
import json
import pytest
from chat_hpc_control.contracts.results import OutputSnapshot


@pytest.fixture
def snapshot(tmp_path):
    def make(files, options=None):
        for name, value in files.items():
            path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(value)
        (tmp_path/'task-manifest.json').write_text(json.dumps({'task':{'engine_options':options or {}}}))
        rows=[{'path':p.name,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
              for p in tmp_path.iterdir() if p.is_file()]
        return OutputSnapshot(tmp_path,rows,'a'*64,{'execution_state':'COMPLETED'})
    return make


@pytest.fixture
def record():
    return {'record_id':'h2','atom_symbols':['H','H'],'coordinates':[[0,0,0],[0,0,.74]],
            'geometry_unit':'angstrom','charge':0,'multiplicity':1,'method':'RHF','basis':'STO-3G',
            'state_id':'ground','energy':-1.1,'energy_unit':'hartree','gradient':[[0,0,.1],[0,0,-.1]],
            'gradient_unit':'hartree/bohr','converged':True,'program_version':'synthetic-test'}
