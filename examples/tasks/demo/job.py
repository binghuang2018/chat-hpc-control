"""Synthetic protocol demonstration, not a scientific calculation."""
import json
from pathlib import Path
Path('records.json').write_text(json.dumps({'records':[{'record_id':'demo-0','energy':0.0,'synthetic':True}]}))
print('synthetic demo completed')
