"""Tiny RHF/STO-3G integration example; results are script-reported."""
import json
from pathlib import Path
import pyscf
from pyscf import gto,scf

mol=gto.M(atom='geometry.xyz',basis='sto-3g',charge=0,spin=0,unit='Angstrom',verbose=3)
mol.max_memory=256
mf=scf.RHF(mol);mf.conv_tol=1e-10
energy=mf.kernel()
if not mf.converged:raise RuntimeError('SCF did not converge')
gradient=mf.nuc_grad_method().kernel()
record={'record_id':'h2-0','atom_symbols':[mol.atom_symbol(i) for i in range(mol.natm)],
        'coordinates':mol.atom_coords(unit='Angstrom').tolist(),'geometry_unit':'angstrom',
        'charge':mol.charge,'multiplicity':mol.spin+1,'method':'RHF','basis':'STO-3G','state_id':'ground',
        'energy':float(energy),'energy_unit':'hartree','gradient':gradient.tolist(),'gradient_unit':'hartree/bohr',
        'converged':bool(mf.converged),'program_version':pyscf.__version__}
Path('records.json').write_text(json.dumps({'schema':'chat-hpc-control/pyscf-records/v1','records':[record]},allow_nan=False))
