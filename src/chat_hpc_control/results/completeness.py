"""All declared records/quantities must match; no inference from output count."""

import math
from ..engines.parsers.common import read

BOHR_ANGSTROM=0.529177210903


def assess(snapshot,report,contract):
    issues=[dict(i) for i in report.issues]
    def issue(code,severity='invalid',rid=None):
        issues.append({'code':code,'severity':severity,**({'record_id':rid} if rid else {})})
    if not contract:issue('NO_DECLARED_CONTRACT','unverified')
    if not report.supported:issue('PROFILE_UNSUPPORTED','unverified')
    actual={}
    for record in report.records:
        rid=record.get('record_id')
        if not isinstance(rid,str) or rid in actual:issue('DUPLICATE_OR_INVALID_RECORD_ID',rid=rid)
        else:actual[rid]=record
    expected={r['record_id']:r for r in (contract or {}).get('records',[])}
    if contract:
        for rid in actual.keys()-expected.keys():issue('EXTRA_RECORD',rid=rid)
    def numeric(x):return type(x) in (float,int) and math.isfinite(x)
    def matrix(value,n):
        return (isinstance(value,list) and len(value)==n and all(isinstance(r,list) and len(r)==3
                and all(numeric(x) for x in r) for r in value))
    for rid,declared in expected.items():
        record=actual.get(rid)
        if record is None:
            issue('MISSING_RECORD','incomplete',rid);continue
        for key in ('atom_symbols','charge','multiplicity','method','basis','state_id'):
            if key not in record:issue('MISSING_METADATA_'+key.upper(),'unverified',rid)
            elif record[key]!=declared[key] or (key in {'charge','multiplicity'} and type(record[key])!=int):
                issue('METADATA_MISMATCH_'+key.upper(),rid=rid)
        if not record.get('program_version'):issue('PROGRAM_VERSION_MISSING','unverified',rid)
        if 'converged' not in record:issue('CONVERGENCE_EVIDENCE_MISSING','unverified',rid)
        elif record['converged'] is not True:issue('NOT_CONVERGED',rid=rid)
        sources=record.get('raw_sources')
        if not isinstance(sources,list) or not sources:issue('RAW_SOURCE_MISSING','unverified',rid)
        else:
            for source in sources:
                try:
                    if not source.get('locator'):raise ValueError('locator missing')
                    read(snapshot,source['path'])
                except (OSError,ValueError,KeyError,TypeError,AttributeError):issue('RAW_SOURCE_UNAVAILABLE','unverified',rid)
        n=len(declared['atom_symbols'])
        if 'coordinates' not in record:issue('GEOMETRY_EVIDENCE_MISSING','unverified',rid)
        elif not matrix(record['coordinates'],n):issue('GEOMETRY_SHAPE_OR_NUMBER_INVALID',rid=rid)
        elif record.get('geometry_unit') not in {'angstrom','bohr'}:issue('GEOMETRY_UNIT_INVALID',rid=rid)
        else:
            try:
                lines=read(snapshot,'inputs/'+declared['geometry_file']).decode('utf-8').splitlines()
                if int(lines[0])!=n or len(lines)!=n+2:raise ValueError('XYZ size mismatch')
                atoms=[line.split() for line in lines[2:]]
                if any(len(a)!=4 for a in atoms) or [a[0] for a in atoms]!=declared['atom_symbols']:raise ValueError('XYZ order')
                target=[[float(x) for x in a[1:]] for a in atoms]
                input_factor=1/BOHR_ANGSTROM if declared['geometry_unit']=='angstrom' else 1
                output_factor=1/BOHR_ANGSTROM if record['geometry_unit']=='angstrom' else 1
                if (not matrix(target,n) or any(abs(x*input_factor-y*output_factor)>1e-5
                      for a,b in zip(target,record['coordinates']) for x,y in zip(a,b))):issue('GEOMETRY_MISMATCH',rid=rid)
            except (OSError,ValueError,KeyError,IndexError,TypeError):issue('INPUT_GEOMETRY_UNVERIFIED','unverified',rid)
        for quantity in declared['quantities']:
            if quantity not in record:
                issue('MISSING_'+quantity.upper(),'incomplete',rid);continue
            if quantity=='energy':
                if not numeric(record['energy']):issue('ENERGY_NUMBER_INVALID',rid=rid)
                if record.get('energy_unit')!='hartree':issue('ENERGY_UNIT_INVALID',rid=rid)
            if quantity=='gradient':
                if not matrix(record['gradient'],n):issue('GRADIENT_SHAPE_OR_NUMBER_INVALID',rid=rid)
                if record.get('gradient_unit')!='hartree/bohr':issue('GRADIENT_UNIT_INVALID',rid=rid)
    levels={i.get('severity','unverified') for i in issues}
    completeness=('INVALID' if 'invalid' in levels else 'UNVERIFIED' if 'unverified' in levels
                  else 'INCOMPLETE' if 'incomplete' in levels else 'COMPLETE')
    state=snapshot.terminal.get('execution_state','UNKNOWN')
    integrity=snapshot.terminal.get('integrity','UNVERIFIED')
    return {'execution_state':state,'integrity':integrity,'completeness':completeness,
            'scientific_acceptance':'NOT_EVALUATED','data_ready':state=='COMPLETED' and integrity=='VERIFIED' and completeness=='COMPLETE',
            'issues':issues,'expected_count':len(expected),'actual_count':len(report.records)}
