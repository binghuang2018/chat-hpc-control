from copy import deepcopy
from dataclasses import replace
import importlib
import pytest


def assess(*args):
    try:return importlib.import_module('chat_hpc_control.results.completeness').assess(*args)
    except ModuleNotFoundError:pytest.fail('completeness assessor missing')


def test_complete_is_not_scientific_acceptance(quantity_case):
    result=assess(*quantity_case)
    assert result['data_ready'] is True
    assert result['scientific_acceptance']=='NOT_EVALUATED'
    assert result['completeness']=='COMPLETE'


@pytest.mark.parametrize('mutation,status',[
 ('missing_energy','INCOMPLETE'),('missing_gradient','INCOMPLETE'),('bad_shape','INVALID'),('extra_record','INVALID'),
 ('duplicate_id','INVALID'),('wrong_unit','INVALID'),('wrong_atom_order','INVALID'),('wrong_geometry','INVALID'),
 ('wrong_method','INVALID'),('wrong_state','INVALID'),('nonfinite','INVALID'),('not_converged','INVALID'),
 ('missing_evidence','UNVERIFIED'),('boolean_energy','INVALID')])
def test_quantity_matrix(quantity_case,mutation,status):
    snap,report,contract=deepcopy(quantity_case);record=report.records[0]
    if mutation=='missing_energy':record.pop('energy')
    if mutation=='missing_gradient':record.pop('gradient')
    if mutation=='bad_shape':record['gradient']=[[0,0,0]]
    if mutation=='extra_record':report.records.append({**record,'record_id':'extra'})
    if mutation=='duplicate_id':report.records.append(dict(record))
    if mutation=='wrong_unit':record['gradient_unit']='eV/angstrom'
    if mutation=='wrong_atom_order':record['atom_symbols']=['He','H']
    if mutation=='wrong_geometry':record['coordinates'][1][2]=1
    if mutation=='wrong_method':record['method']='PBE0'
    if mutation=='wrong_state':record['state_id']='excited'
    if mutation=='nonfinite':record['energy']=float('nan')
    if mutation=='not_converged':record['converged']=False
    if mutation=='missing_evidence':record.pop('raw_sources')
    if mutation=='boolean_energy':record['energy']=True
    result=assess(snap,report,contract)
    assert result['completeness']==status,result
    assert result['data_ready'] is False
    assert result['issues']


def test_dimensions_are_independent(quantity_case):
    snap,report,contract=quantity_case
    assert assess(snap,report,None)['completeness']=='UNVERIFIED'
    assert assess(snap,replace(report,supported=False),contract)['data_ready'] is False
    failed=replace(snap,terminal={'execution_state':'FAILED','integrity':'VERIFIED'})
    result=assess(failed,report,contract)
    assert result['completeness']=='COMPLETE' and not result['data_ready']
    assert assess(replace(snap,terminal={'execution_state':'COMPLETED','integrity':'FAILED'}),report,contract)['data_ready'] is False


def test_exact_unit_geometry_conversion(quantity_case):
    snap,report,contract=quantity_case
    report.records[0]['coordinates'][1][2]=.74/.529177210903
    report.records[0]['geometry_unit']='bohr'
    assert assess(snap,report,contract)['data_ready']


def test_missing_geometry_evidence_is_unverified(quantity_case):
    snap,report,contract=quantity_case
    report.records[0].pop('coordinates')
    assert assess(snap,report,contract)['completeness']=='UNVERIFIED'
