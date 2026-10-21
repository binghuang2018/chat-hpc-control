import importlib
import pytest


def parse(name,snap):
    try: return importlib.import_module('chat_hpc_control.engines.parsers.molpro_'+name).parse(snap,{'records':[{'record_id':'h2'}]})
    except ModuleNotFoundError: pytest.fail('Molpro parser missing')

TABLE='''record_id,method,basis,state_id,element,geometry_unit,energy_unit,gradient_unit,program_version,charge,multiplicity,atom_index,x,y,z,energy,gx,gy,gz,converged
h2,RHF,STO-3G,ground,H,angstrom,hartree,hartree/bohr,synthetic,0,1,1,0,0,0,-1.1,0,0,.1,1
h2,RHF,STO-3G,ground,H,angstrom,hartree,hartree/bohr,synthetic,0,1,2,0,0,.74,-1.1,0,0,-.1,1
'''
XML='''<molpro xmlns="http://www.molpro.net/schema/molpro-output" xmlns:c="http://www.xml-cml.org/schema" version="synthetic"><job><molecule><c:molecule formalCharge="0" spinMultiplicity="1"><c:atomArray><c:atom elementType="H" x3="0" y3="0" z3="0"/><c:atom elementType="H" x3="0" y3="0" z3=".74"/></c:atomArray></c:molecule><basisSet id="STO-3G"/></molecule><jobstep command="RHF" converged="true"><property name="Energy" method="RHF" state="ground" value="-1.1" units="hartree"/><gradient method="RHF" state="ground" units="hartree/bohr">0 0 .1 0 0 -.1</gradient></jobstep></job></molpro>'''


def test_named_native_table(snapshot):
    report=parse('table',snapshot({'results.csv':TABLE}))
    assert report.supported and not report.issues,report
    assert report.records[0]['gradient']==[[0,0,.1],[0,0,-.1]]
    assert report.records[0]['evidence_level']=='table-reported'


def test_table_does_not_merge_different_methods(snapshot):
    report=parse('table',snapshot({'results.csv':TABLE.replace('h2,RHF,STO-3G,ground,H,angstrom,hartree,hartree/bohr,synthetic,0,1,2','h2,CCSD,STO-3G,ground,H,angstrom,hartree,hartree/bohr,synthetic,0,1,2')}))
    assert any(i.get('severity')=='invalid' for i in report.issues)


def test_xml_complete_geometry_and_bound_gradient(snapshot):
    report=parse('xml',snapshot({'job.xml':XML}))
    assert report.supported and not report.issues,report
    assert len(report.records[0]['coordinates'])==2


@pytest.mark.parametrize('raw',[XML.replace('method="RHF" state="ground" units="hartree/bohr"','units="hartree/bohr"'), XML.replace('<gradient','<gradient').replace('</jobstep>','<property name="Energy" method="CCSD" state="ground" value="-1.2" units="hartree"/></jobstep>')])
def test_xml_never_guesses_gradient_method(snapshot,raw):
    report=parse('xml',snapshot({'job.xml':raw}))
    assert report.issues and (not report.supported or any(i.get('severity')=='invalid' for i in report.issues))


def test_xml_entities_rejected(snapshot):
    report=parse('xml',snapshot({'job.xml':'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><molpro>&secret;</molpro>'}))
    assert not report.supported and report.issues


def test_xml_missing_convergence_is_not_certified(snapshot):
    report=parse('xml',snapshot({'job.xml':XML.replace(' converged="true"','')}))
    assert not report.supported
