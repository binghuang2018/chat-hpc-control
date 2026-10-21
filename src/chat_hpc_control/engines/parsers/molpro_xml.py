"""Strict single-step XML subset; gradient method/state must be explicit."""

import xml.etree.ElementTree as ET
from .common import read,options,report,failure

NS={'m':'http://www.molpro.net/schema/molpro-output','c':'http://www.xml-cml.org/schema'}


def parse(snapshot,contract):
    profile='molpro-xml-single-v1'
    try:
        names=[r['path'] for r in snapshot.files if r['path'].endswith('.xml')]
        name=options(snapshot).get('output_file')
        if name is None:
            if len(names)!=1:return failure(profile,'MOLPRO_XML_AMBIGUOUS')
            name=names[0]
        raw=read(snapshot,name)
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():return failure(profile,'XML_ENTITIES_REJECTED','invalid')
        root=ET.fromstring(raw)
        molecules=root.findall('.//c:molecule',NS)
        if len(molecules)!=1:return failure(profile,'MOLPRO_XML_GEOMETRY_AMBIGUOUS')
        molecule=molecules[0];atoms=molecule.findall('c:atomArray/c:atom',NS)
        # Parse every coordinate before any gradient can be associated.
        coords=[[float(a.attrib[k]) for k in ('x3','y3','z3')] for a in atoms]
        if not coords:return failure(profile,'MOLPRO_XML_GEOMETRY_MISSING')
        steps=root.findall('.//m:jobstep',NS)
        if len(steps)!=1:return failure(profile,'MOLPRO_XML_STEPS_AMBIGUOUS','invalid')
        step=steps[0]
        if step.get('converged')!='true':return failure(profile,'MOLPRO_XML_CONVERGENCE_UNPROVEN')
        energies=[p for p in step.findall('m:property',NS) if p.get('name')=='Energy']
        if len(energies)!=1:return failure(profile,'MOLPRO_XML_ENERGY_AMBIGUOUS','invalid')
        energy=energies[0];method=energy.attrib['method'];state=energy.attrib['state']
        if step.get('command')!=method:return failure(profile,'MOLPRO_XML_METHOD_UNBOUND','invalid')
        bases=root.findall('.//m:basisSet',NS)
        if len(bases)!=1 or not contract or len(contract.get('records',[]))!=1:return failure(profile)
        rec={'record_id':contract['records'][0]['record_id'],'method':method,'basis':bases[0].attrib['id'],
             'state_id':state,'charge':int(molecule.attrib['formalCharge']),'multiplicity':int(molecule.attrib['spinMultiplicity']),
             'atom_symbols':[a.attrib['elementType'] for a in atoms],'coordinates':coords,'geometry_unit':'angstrom',
             'energy':float(energy.attrib['value']),'energy_unit':energy.attrib['units'],
             'program_version':root.attrib['version'],'converged':True,'evidence_level':'native-xml-subset',
             'raw_sources':[{'path':name,'locator':'single jobstep/property and cml:molecule'}]}
        gradients=step.findall('m:gradient',NS)
        if len(gradients)>1:return failure(profile,'MOLPRO_XML_GRADIENT_AMBIGUOUS','invalid')
        if gradients:
            g=gradients[0]
            if g.get('method')!=method or g.get('state')!=state:return failure(profile,'MOLPRO_XML_GRADIENT_UNBOUND','invalid')
            values=[float(x) for x in (g.text or '').split()]
            if len(values)!=3*len(atoms):return failure(profile,'MOLPRO_XML_GRADIENT_SIZE','invalid')
            rec.update(gradient=[values[i:i+3] for i in range(0,len(values),3)],gradient_unit=g.attrib['units'])
        return report(profile,[rec])
    except (OSError,ValueError,KeyError,TypeError,ET.ParseError):
        return failure(profile,'MOLPRO_XML_PROFILE_UNREADABLE')
