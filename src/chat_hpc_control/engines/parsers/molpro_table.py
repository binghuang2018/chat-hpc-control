"""Explicit named Molpro TABLE CSV contract, one ordered row per atom."""

import csv
import io
import math
from .common import read,options,report,failure


def parse(snapshot,contract):
    profile='molpro-table-v1'
    try:
        name=options(snapshot).get('result_file','results.csv')
        reader=csv.DictReader(io.StringIO(read(snapshot,name).decode('utf-8')))
        if not reader.fieldnames or len(set(x.lower() for x in reader.fieldnames))!=len(reader.fieldnames):
            return failure(profile,'MOLPRO_TABLE_HEADER_INVALID','invalid')
        groups={}
        for raw in reader:
            row={k.strip().lower():v.strip() for k,v in raw.items()}
            groups.setdefault(row['record_id'],[]).append(row)
        records=[]
        metadata=('record_id','method','basis','state_id','geometry_unit','energy_unit','gradient_unit',
                  'program_version','charge','multiplicity','energy','converged')
        for rid,rows in groups.items():
            first=rows[0]
            if any(any(row[k]!=first[k] for k in metadata) for row in rows):
                return failure(profile,'MOLPRO_TABLE_METHOD_OR_STATE_AMBIGUOUS','invalid')
            if [int(r['atom_index']) for r in rows]!=list(range(1,len(rows)+1)):
                return failure(profile,'MOLPRO_TABLE_ATOM_ORDER_INVALID','invalid')
            rec={k:first[k] for k in ('record_id','method','basis','state_id','geometry_unit','energy_unit','program_version')}
            rec.update(charge=int(first['charge']),multiplicity=int(first['multiplicity']),energy=float(first['energy']),
                       atom_symbols=[r['element'] for r in rows],coordinates=[[float(r[k]) for k in ('x','y','z')] for r in rows],
                       converged=first['converged']=='1',evidence_level='table-reported',
                       raw_sources=[{'path':name,'locator':'record_id='+rid}])
            if any(any(r.get(k,'') for k in ('gx','gy','gz')) for r in rows):
                rec.update(gradient=[[float(r[k]) for k in ('gx','gy','gz')] for r in rows],gradient_unit=first['gradient_unit'])
            values=[rec['energy'],*(x for row in rec['coordinates'] for x in row),*(x for row in rec.get('gradient',[]) for x in row)]
            if not all(math.isfinite(x) for x in values):return failure(profile,'MOLPRO_TABLE_NONFINITE','invalid')
            records.append(rec)
        return report(profile,records)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        return failure(profile,'MOLPRO_TABLE_UNREADABLE')
