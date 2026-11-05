#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise native row restoration under the real configuration-loader scope.

PDN itself is replaced by a local success/failure stub. This checks the
metadata hook only and cannot qualify a physical grid or electrical result.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import librelane
import harden_weighted_bank_v17 as parent_flow

ROOT=parent_flow.ROOT
sha=parent_flow.sha
VERSION='native-row-restore-powered-site-blockage-contract-v2.3'


def run(parent):
    m=parent_flow.bound(parent);r=json.loads((parent/'summary.json').read_text())
    folder=ROOT/r['run'];db=folder/'19-openroad-tapendcapinsertion/openlvds_weighted_bank_physical_v2.odb';env=folder/'21-openroad-generatepdn/_env.tcl'
    scripts=Path(librelane.__file__).parent/'scripts'
    paths=[Path(__file__),Path(parent_flow.__file__),parent/'manifest.json',parent/'summary.json',db,env,
        scripts/'openroad/common/set_global_connections.tcl']
    paths += [ROOT/'constraints/v2'/n for n in ['weighted_bank_pdn_v15.tcl','weighted_bank_pdn_v17.tcl','weighted_bank_pdn_v18.tcl','weighted_bank_pdn_v19.tcl']]
    paths += [ROOT/'scripts'/n for n in ['weighted_bank_row_restore_v2.py','weighted_bank_row_restore_v3.py','weighted_bank_row_strip_v3.py','weighted_bank_row_restore_v4.py']]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in paths},tools=parent_flow.old.tool_identity())
    out=ROOT/'build/diagnostics/weighted_bank_row_restore_contract_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);parent_flow.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));rows=[]
    for name,config,fail in [('old_scope',17,False),('successful_generation',19,False),('failed_generation',19,True)]:
        work=out/name;work.mkdir();script=work/'check.tcl'
        script.write_text(f'''set ::env(SCRIPTS_DIR) {{{scripts}}}
source {{{env}}}
set ::env(VDD_NET) VPWR
set ::env(GND_NET) VGND
read_db {{{db}}}
proc contract_dump_rows {{path}} {{
  set f [open $path w]
  foreach row [[ord::get_db_block] getRows] {{
    set b [$row getBBox]
    puts $f "[$row getName]\\t[[$row getSite] getName]\\t[$row getOrigin]\\t[$row getOrient]\\t[$row getDirection]\\t[$row getSiteCount]\\t[$row getSpacing]\\t[$b xMin]\\t[$b yMin]\\t[$b xMax]\\t[$b yMax]"
  }}
  close $f
}}
proc contract_dump_blockages {{path}} {{
  set f [open $path w]
  foreach b [[ord::get_db_block] getBlockages] {{
    set r [$b getBBox]
    puts $f "[$r xMin]\\t[$r yMin]\\t[$r xMax]\\t[$r yMax]\\t[$b isSoft]"
  }}
  close $f
}}
contract_dump_blockages blockages_before.tsv
contract_dump_rows before.tsv
rename pdngen native_pdngen
proc pdngen {{}} {{
  {'error "injected generation failure"' if fail else 'return'}
}}
proc load_configuration {{}} {{source {{{ROOT/'constraints/v2'/('weighted_bank_pdn_v'+str(config)+'.tcl')}}}}}
load_configuration
contract_dump_rows sparse.tsv
set status [catch {{pdngen}} result]
contract_dump_rows after.tsv
contract_dump_blockages blockages_after.tsv
set f [open result.tsv w]
puts $f "$status\\t$result"
close $f
exit
''')
        with (work/'check.log').open('w') as log:p=subprocess.run(['openroad','-no_init','-exit',str(script)],cwd=work,stdout=log,stderr=subprocess.STDOUT)
        def records(n):return Counter((work/n).read_text().splitlines()) if (work/n).exists() else Counter()
        before,sparse,after=[records(n+'.tsv') for n in ['before','sparse','after']]
        status=(work/'result.tsv').read_text().rstrip('\n').split('\t',1) if (work/'result.tsv').exists() else []
        valid=p.returncode==0 and sum(before.values())>sum(sparse.values())>0 and len(status)==2
        if name=='old_scope':passed=valid and status[0]=='1' and 'strip_block' in status[1] and after==sparse
        elif fail:passed=valid and status==['1','injected generation failure'] and after==sparse
        else:
            expected=Counter('\t'.join(line.split('\t')[-4:]+['0']) for line,n in (before-sparse).items() for _ in range(n))
            blocked=records('blockages_after.tsv')-records('blockages_before.tsv')
            passed=valid and status[0]=='0' and after==before and blocked==expected and bool(blocked)
        rows.append(dict(case=name,returncode=p.returncode,rows_before=sum(before.values()),rows_sparse=sum(sparse.values()),rows_after=sum(after.values()),added_placement_blockages=sum((records('blockages_after.tsv')-records('blockages_before.tsv')).values()),status=status,passed=passed))
    if any(sha(Path(n) if Path(n).is_absolute() else ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Row contract inputs changed')
    result=dict(rows=rows,passed=all(x['passed'] for x in rows),qualified_phy=False,power_grid_qualification_passed=False,
        scope='Native OpenDB row metadata and loader-scope success/failure hook only; stubbed PDN, no physical connectivity, geometry or electrical qualification',
        files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'})
    parent_flow.atomic(out/'summary.json',result);print(out,flush=True);print(json.dumps(result,indent=2),flush=True)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);a=p.parse_args();run(a.parent.resolve())
