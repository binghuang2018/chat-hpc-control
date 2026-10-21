"""Exact atom count, energy, 3N gradient and ordered atomic-number geometry."""

import math
from .common import read


def extract(snapshot,name):
    lines=[line.strip() for line in read(snapshot,name).decode('utf-8').splitlines()
           if line.strip() and not line.lstrip().startswith('#')]
    n=int(lines[0])
    if n<=0 or len(lines)!=2+4*n: raise ValueError('truncated or extra engrad data')
    energy=float(lines[1]);gradient=[float(v) for v in lines[2:2+3*n]]
    atoms=[line.split() for line in lines[2+3*n:]]
    if any(len(a)!=4 for a in atoms): raise ValueError('invalid engrad geometry')
    numbers=[int(a[0]) for a in atoms];xyz=[[float(x) for x in a[1:]] for a in atoms]
    if not all(math.isfinite(x) for x in [energy,*gradient,*(v for row in xyz for v in row)]):
        raise ValueError('nonfinite engrad value')
    return energy,[gradient[i:i+3] for i in range(0,3*n,3)],numbers,xyz


def parse(snapshot,contract):
    from .orca_single import parse as single
    return single(snapshot,contract,profile='orca-engrad-v1')
