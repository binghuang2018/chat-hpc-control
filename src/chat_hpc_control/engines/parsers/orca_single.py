"""One RHF singlet single point, explicit native metadata, no method guessing."""

import math
import re
from .common import read,options,report,failure
from .orca_engrad import extract

# All 118 IUPAC symbols, only for checking native .engrad atomic numbers.
ELEMENTS=('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn '
'Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd '
'Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac '
'Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og').split()


def parse(snapshot,contract,*,profile='orca-single-v1'):
    try:
        opt=options(snapshot);name=opt.get('output_file','stdout.log')
        text=read(snapshot,name).decode('utf-8')
        def one(pattern):
            matches=re.findall(pattern,text,re.MULTILINE)
            if len(matches)!=1: raise ValueError('missing or ambiguous native metadata')
            return matches[0].strip()
        energies=re.findall(r'^\s*FINAL SINGLE POINT ENERGY\s+(\S+)\s*$',text,re.MULTILINE)
        if len(energies)>1:return failure(profile,'ORCA_MULTIPLE_ENERGIES','invalid')
        method=one(r'^\s*Hartree-Fock type\s+HFTyp\s+\.*\s+(\S+)\s*$')
        multiplicity=int(one(r'^\s*Multiplicity\s+Mult\s+\.*\s+(\d+)\s*$'))
        # Correlated, DFT, excited-state and multi-step output require another profile.
        if (method!='RHF' or multiplicity!=1 or re.search(r'(?im)^.*(?:DFT calculation|DLPNO-|E\(MP2\)|COUPLED CLUSTER|TD-DFT|CASSCF)',text)):
            return failure(profile,'ORCA_METHOD_OUTSIDE_PROFILE')
        if len(energies)!=1: return failure(profile,'ORCA_ENERGY_MISSING')
        energy=float(energies[0]);basis=one(r'^\s*Your calculation utilizes the basis:\s*(\S+)\s*$')
        charge=int(one(r'^\s*Total Charge\s+Charge\s+\.*\s+(-?\d+)\s*$'))
        version=one(r'^\s*Program Version\s+(.+)$')
        block=one(r'CARTESIAN COORDINATES \(ANGSTROEM\)\s*\n[- ]+\n([\s\S]*?)\n\s*\n')
        atoms=[line.split() for line in block.splitlines()]
        if not atoms or any(len(a)!=4 or a[0] not in ELEMENTS for a in atoms): raise ValueError('bad geometry')
        coords=[[float(x) for x in a[1:]] for a in atoms]
        if not all(math.isfinite(x) for x in [energy,*(x for r in coords for x in r)]):raise ValueError('nonfinite')
        if not contract or len(contract.get('records',[]))!=1:return failure(profile,'ORCA_SINGLE_RECORD_REQUIRED')
        rec={'record_id':contract['records'][0]['record_id'],'method':'RHF','basis':basis,'state_id':'ground',
             'charge':charge,'multiplicity':multiplicity,'atom_symbols':[a[0] for a in atoms],
             'coordinates':coords,'geometry_unit':'angstrom','energy':energy,'energy_unit':'hartree',
             'program_version':version,'converged':'SCF CONVERGED AFTER' in text,
             'evidence_level':'native-output','raw_sources':[{'path':name,'locator':'single RHF block'}]}
        if profile=='orca-engrad-v1':
            names=[r['path'] for r in snapshot.files if r['path'].endswith('.engrad')]
            gradname=opt.get('gradient_file')
            if gradname is None:
                if len(names)!=1:return failure(profile,'ORCA_ENGRAD_AMBIGUOUS')
                gradname=names[0]
            e,grad,numbers,xyz=extract(snapshot,gradname)
            if (numbers!=[ELEMENTS.index(a[0])+1 for a in atoms] or abs(e-energy)>1e-8
                    or any(abs(x/0.529177210903-y)>1e-5 for a,b in zip(coords,xyz) for x,y in zip(a,b))):
                return failure(profile,'ORCA_ENGRAD_BINDING_MISMATCH','invalid')
            rec.update(gradient=grad,gradient_unit='hartree/bohr')
            rec['raw_sources'].append({'path':gradname,'locator':'ordered gradient and atomic geometry'})
        return report(profile,[rec])
    except (OSError,ValueError,KeyError,TypeError,IndexError):
        return failure(profile,'ORCA_PROFILE_UNREADABLE')
