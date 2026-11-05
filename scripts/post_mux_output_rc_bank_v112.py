# SPDX-License-Identifier: GPL-3.0-only
"""Replace ideal tied final inverter ports with a native compound RC master."""
import hashlib
import json
import re
import post_mux_regeneration_v108 as base
import exact_rc_candidate as exact
from parallel_root_bank_v97 import rename
from build_compound_drivers_v3 import cell_definition

ROOT=base.ROOT
source=base.source
checked_cell=base.checked_cell
DRIVER_PARENT=ROOT/'build/diagnostics/parallel_output_cell_v111/719aa3336298176d'
DRIVER='openlvds_parallel_inv8_v110'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def name(profile):
    base.name(profile)
    return 'openlvds_post_mux_output_rc_'+profile+'_v112'


def driver_inputs():
    p=DRIVER_PARENT;i=json.loads((p/'manifest.json').read_text())['identity'];r=json.loads((p/'summary.json').read_text())
    return [p/'manifest.json',p/'summary.json',p/'state.json',
            *[ROOT/n for n in i['inputs']],*[p/n for n in r['files']],*[ROOT/n for n in r['extracted_files']]]


def checked_driver():
    p=DRIVER_PARENT;i=json.loads((p/'manifest.json').read_text())['identity'];r=json.loads((p/'summary.json').read_text())
    if (p.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['version']!='parallel-native-inv8-gds-junctions-and-full-component-rc-v111.1'
        or exact.math_runtime()!=i['math_runtime']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(p/n)!=h for n,h in r['files'].items())
        or any(sha(ROOT/n)!=h for n,h in r['extracted_files'].items())
        or json.loads((p/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['parallel_output_component_passed'] or len(r['rows'])!=1 or r['qualified_phy']):
        raise ValueError('Require unchanged complete physical parallel output component')
    row=r['rows'][0];proof=row['rc_proof'];info=row['extraction']
    if (row['profile']!='inv2' or not row['physical']['passed']
        or row['placement_geometry']['drc_count']!='0'
        or row['native_parameters']['native_primitives']!=34
        or not proof['component_rc_passed'] or not proof['native_topology_verified']
        or not proof['independent_terminal_current_witness']['proof']['passed']):
        raise ValueError('Parallel output component qualification failed')
    text=(ROOT/info['netlist']).read_text()
    if sha(ROOT/info['netlist'])!=info['netlist_sha256']:
        raise ValueError('Parallel output RC changed')
    ports=source.native.definitions(text)[DRIVER][0]
    if ports!=['IN','OUT','VPWR','VGND']:
        raise ValueError('Parallel output interface changed')
    return text


def substitute(bank,top,driver_rc):
    """Only change the pair of final calls; preserve every other byte."""
    defs=source.native.definitions(bank)
    if DRIVER in defs:
        raise ValueError('Parallel output component already present')
    before=cell_definition(bank,top);body=defs[top][1]
    calls={tag:[w for w in body if w[0]==tag] for tag in ['Xfine_driver','Xfine_parallel']}
    for tag,rows in calls.items():
        if len(rows)!=1 or rows[0][-1]!=base.INV or dict(zip(defs[base.INV][0],rows[0][1:-1]))!=dict(A='fine_slow',Y='OUT',VGND='VGND',VPWR='VPWR'):
            raise ValueError('Expected exactly two final inverters on the common fine node')
    after=before
    for tag,rows in calls.items():
        line=' '.join(rows[0])+'\n'
        if after.count(line)!=1:raise ValueError('Ambiguous final inverter source')
        after=after.replace(line,'Xfine_compound fine_slow OUT VPWR VGND '+DRIVER+'\n' if tag=='Xfine_driver' else '',1)
    return bank.replace(before,after,1)+'\n'+cell_definition(driver_rc,DRIVER)


def transform(text,profile,fine_rc):
    original=base.transform(text,profile,fine_rc)
    bank=rename(substitute(original,base.name(profile),checked_driver()),base.name(profile),name(profile))
    counts=source.primitive_counts(bank,name(profile))
    if sum(v for k,v in counts.items() if 'fet_' in k)!=981 or counts.get('sky130_fd_pr__cap_mim_m3_1')!=35:
        raise ValueError('Measured output compound changed native bank inventory')
    return bank


def observations(bank,profile,previous):
    # Top/unit definition names do not affect native XD instance/node paths.
    return base.observations(rename(bank,name(profile),base.name(profile)),profile,previous)
