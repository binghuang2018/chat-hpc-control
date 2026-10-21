import importlib
from pathlib import Path
import pytest
FIXTURES=Path(__file__).parents[1]/'fixtures/qc'

def parse(snap,profile='orca-single-v1'):
    try: return importlib.import_module('chat_hpc_control.engines.parsers.orca_single').parse(snap,{'records':[{'record_id':'h2'}]},profile=profile)
    except ModuleNotFoundError: pytest.fail('ORCA parser missing')


def test_native_energy_and_gradient(snapshot):
    snap=snapshot({'stdout.log':(FIXTURES/'orca-rhf.out').read_text(),'job.engrad':(FIXTURES/'orca-rhf.engrad').read_text()})
    result=parse(snap,'orca-engrad-v1')
    assert result.supported and not result.issues,result
    assert result.records[0]['method']=='RHF'
    assert result.records[0]['gradient']==[[0,0,.1],[0,0,-.1]]
    assert result.records[0]['atom_symbols']==['H','H']


@pytest.mark.parametrize('alter',[lambda x:x.replace('RHF','RKS'),lambda x:x.replace('Mult .... 1','Mult .... 3')])
def test_unsupported_method_is_unverified(snapshot,alter):
    result=parse(snapshot({'stdout.log':alter((FIXTURES/'orca-rhf.out').read_text())}))
    assert not result.supported and not result.records


def test_multiple_energies_are_ambiguous(snapshot):
    raw=(FIXTURES/'orca-rhf.out').read_text()
    result=parse(snapshot({'stdout.log':raw+'\nFINAL SINGLE POINT ENERGY -1.2\n'}))
    assert any(i.get('severity')=='invalid' for i in result.issues)


def test_truncated_engrad(snapshot):
    result=parse(snapshot({'stdout.log':(FIXTURES/'orca-rhf.out').read_text(),'job.engrad':'2\n-1.1\n0\n'}),'orca-engrad-v1')
    assert result.issues
