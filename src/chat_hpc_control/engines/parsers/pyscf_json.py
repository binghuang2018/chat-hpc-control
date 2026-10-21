"""Script-reported PySCF JSON, never independent scientific certification."""

from ...contracts.codec import decode_json
from .common import read,options,report,failure


def parse(snapshot,contract):
    profile='pyscf-json-v1'
    try:
        name=options(snapshot).get('result_file','records.json')
        data=decode_json(read(snapshot,name))
        if data.get('schema')!='chat-hpc-control/pyscf-records/v1' or not isinstance(data.get('records'),list):
            return failure(profile,'PYSCF_RECORD_SCHEMA_INVALID','invalid')
        records=[]
        for item in data['records']:
            if not isinstance(item,dict): return failure(profile,'PYSCF_RECORD_SCHEMA_INVALID','invalid')
            records.append({**item,'evidence_level':'script-reported',
                            'raw_sources':[{'path':name,'locator':'records/'+str(len(records))}]})
        return report(profile,records)
    except (OSError,ValueError,KeyError,TypeError):
        return failure(profile,'PYSCF_JSON_UNREADABLE','invalid')
