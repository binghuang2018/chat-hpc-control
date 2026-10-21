from copy import deepcopy
import json
import pytest
from chat_hpc_control.contracts.results import OutputSnapshot,ParseReport

@pytest.fixture
def quantity_case(tmp_path):
    (tmp_path/'inputs').mkdir()
    (tmp_path/'inputs/geometry.xyz').write_text('2\nsynthetic\nH 0 0 0\nH 0 0 .74\n')
    contract={'contract':'energy-gradient/v1','records':[{'record_id':'h2','quantities':['energy','gradient'],
        'atom_symbols':['H','H'],'geometry_file':'geometry.xyz','geometry_unit':'angstrom',
        'charge':0,'multiplicity':1,'method':'RHF','basis':'STO-3G','state_id':'ground'}]}
    record={'record_id':'h2','atom_symbols':['H','H'],'coordinates':[[0,0,0],[0,0,.74]],
        'geometry_unit':'angstrom','charge':0,'multiplicity':1,'method':'RHF','basis':'STO-3G','state_id':'ground',
        'energy':-1.1,'energy_unit':'hartree','gradient':[[0,0,.1],[0,0,-.1]],'gradient_unit':'hartree/bohr',
        'program_version':'synthetic','converged':True,'raw_sources':[{'path':'records.json','locator':'records/0'}]}
    (tmp_path/'records.json').write_text(json.dumps({'records':[record]}))
    from chat_hpc_control.sources.bundle import file_records
    inventory=file_records({str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()})
    snap=OutputSnapshot(tmp_path,inventory,'a'*64,{'execution_state':'COMPLETED','integrity':'VERIFIED'})
    return snap,ParseReport('synthetic-v1',{'version':'1','code_sha256':'a'*64},[record]),contract
