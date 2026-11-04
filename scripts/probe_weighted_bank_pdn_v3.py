#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay a held full bank's pre-PDN database with a separately bound grid."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import librelane
import harden_weighted_bank_v5 as prior

ROOT=prior.ROOT
sha=prior.sha
VERSION='weighted-bank-native-pdn-replay-v2.2'


def run(parent,grid):
    m=prior.bound(parent);summary=json.loads((parent/'summary.json').read_text())
    if summary['returncode']==0 or not summary['placement_check']['passed']:
        raise ValueError('Require unchanged placed-interface evidence and held PG failure')
    folder=ROOT/summary['run'];step=folder/'21-openroad-generatepdn'
    db=folder/'19-openroad-tapendcapinsertion/openlvds_weighted_bank_physical_v2.odb'
    env=step/'_env.tcl'
    scripts=Path(librelane.__file__).parent/'scripts'
    files=[scripts/'openroad/common/set_global_connections.tcl',Path(__file__),Path(prior.__file__),parent/'manifest.json',parent/'summary.json',db,env,grid]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),grid=str(grid.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in files},tools=prior.old.tool_identity())
    out=ROOT/'build/diagnostics/weighted_bank_pdn_replay_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);prior.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    script=out/'replay.tcl'
    script.write_text(f'''set ::env(SCRIPTS_DIR) {{{scripts}}}
source {{{env}}}
read_db {{{db}}}
source {{{grid}}}
pdngen -failed_via_report {{{out/'failed_vias.rpt'}}}
set f [open {{{out/'checks.tsv'}}} w]
foreach net {{VPWR VGND}} {{
  set status [catch {{check_power_grid -net $net -error_file {{{out}/$net-errors.rpt}}}} result]
  puts $f "$net\\t$status\\t$result"
}}
close $f
write_db {{{out/'grid.odb'}}}
exit
''')
    with (out/'replay.log').open('w') as log:
        p=subprocess.run(['openroad','-no_init','-exit',str(script)],stdout=log,stderr=subprocess.STDOUT,cwd=out)
    if any(sha(Path(n) if Path(n).is_absolute() else ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('PDN replay inputs changed')
    checks=(out/'checks.tsv').read_text().splitlines() if (out/'checks.tsv').exists() else []
    passed=p.returncode==0 and len(checks)==2 and all(line.split('\t')[1]=='0' for line in checks)
    report=dict(returncode=p.returncode,checks=checks,power_connectivity_passed=passed,qualified_phy=False,
        scope='Pre-PDN database replay only; no detailed placement, signal routes, whole-bank DRC/LVS/RC or electrical qualification',
        files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['manifest.json','summary.json']})
    prior.atomic(out/'summary.json',report);print(out,flush=True);print(json.dumps(report,indent=2),flush=True)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('grid',type=Path);a=p.parse_args();run(a.parent.resolve(),a.grid.resolve())
