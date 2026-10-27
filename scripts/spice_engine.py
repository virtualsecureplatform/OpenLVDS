# SPDX-License-Identifier: GPL-3.0-only
"""Select and identify the actual SPICE engine; never silently substitute one."""
import hashlib
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]

def engine():
    selected=os.environ.get('OPENLVDS_SPICE','xyce')
    if selected not in ['xyce','ngspice']:raise ValueError('Unknown OPENLVDS_SPICE engine')
    return selected

def provenance():
    files=[Path(__file__)]
    if engine()=='ngspice':files.extend([ROOT/'scripts/run_ngspice.py',ROOT/'build/tools/ngspice.json'])
    else:files.append(ROOT/'build/apptainer/openlvds.sif.sha256')
    return hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()

def command(log,deck):
    prefix=['/opt/xyce/bin/Xyce'] if engine()=='xyce' else [sys.executable,str(ROOT/'scripts/run_ngspice.py')]
    return prefix+['-l',str(log),str(deck)]
