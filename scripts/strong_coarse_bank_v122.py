# SPDX-License-Identifier: GPL-3.0-only
"""Match coarse buffer drive to the doubled balanced-bank tap loading.

Retain measured middle-bus fine cells and all original signal stages. Only
coarse/tail buffer components change, to fully extracted native gangs.
"""
import hashlib
import json
import re
from pathlib import Path
import exact_rc_candidate as exact
import balanced_cell_bank_v106 as base
from parallel_root_bank_v97 import rename
from build_compound_drivers_v3 import cell_definition

ROOT=base.ROOT
source=base.source
checked_cell=base.checked_cell
PROFILES=dict(b2=2,b3=3)
BUFFER='openlvds_buf_4_pair_nlvt_v29'
COARSE_PARENT=ROOT/'build/diagnostics/parallel_coarse_cells_v121/be7fd56d4ea74868'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def name(profile):
    if profile not in PROFILES:raise ValueError('Unknown stronger coarse profile')
    return 'openlvds_strong_coarse_'+profile+'_v122'


def component_name(profile):
    name(profile)
    return 'openlvds_parallel_coarse_'+profile+'_v120'


def native_count(profile):return 1133+16*20*(PROFILES[profile]-1)


def coarse_inputs():
    p=COARSE_PARENT;i=json.loads((p/'manifest.json').read_text())['identity'];r=json.loads((p/'summary.json').read_text())
    return [p/'manifest.json',p/'summary.json',p/'state.json',*[ROOT/n for n in i['inputs']],*[p/n for n in r['files']],*[ROOT/n for n in r['extracted_files']]]


def checked_coarse(profile):
    p=COARSE_PARENT;i=json.loads((p/'manifest.json').read_text())['identity'];r=json.loads((p/'summary.json').read_text())
    if (i['version']!='parallel-native-coarse-buffers-gds-junctions-and-full-component-rc-v121.1'
        or p.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or exact.math_runtime()!=i['math_runtime'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(p/n)!=h for n,h in r['files'].items()) or any(sha(ROOT/n)!=h for n,h in r['extracted_files'].items())
        or json.loads((p/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['parallel_coarse_components_passed'] or r['qualified_phy'] or len(r['rows'])!=2):
        raise ValueError('Require complete unchanged native coarse gang qualification')
    rows=[row for row in r['rows'] if row['profile']==profile]
    if len(rows)!=1:raise ValueError('Missing measured coarse component profile')
    row=rows[0];proof=row['rc_proof'];info=row['extraction']
    if (not row['physical']['passed'] or row['placement_geometry']['drc_count']!='0'
        or row['native_parameters']['native_primitives']!=20*PROFILES[profile]
        or not proof['component_rc_passed'] or not proof['native_topology_verified']
        or not proof['independent_terminal_current_witness']['proof']['passed']
        or sha(ROOT/info['netlist'])!=info['netlist_sha256']):raise ValueError('Native coarse component proof failed')
    text=(ROOT/info['netlist']).read_text()
    if source.native.definitions(text)[component_name(profile)][0]!=['IN','OUT','VPWR','VGND']:
        raise ValueError('Native coarse component interface changed')
    return text


def substitute(bank,top,profile,rc):
    defs=source.native.definitions(bank);before=cell_definition(bank,top);seen=set();after=before
    if component_name(profile) in defs:raise ValueError('Stronger coarse bank already composed')
    for w in defs[top][1]:
        match=re.fullmatch(r'Xdelay(\d+)',w[0]);tail=w[0]=='Xtail_load'
        if match is None and not tail:continue
        k=int(match[1]) if match else 16
        expected=dict(A='IN' if k==1 else f'tap{k-1}',X=f'tap{k}' if k<16 else 'unused_tail',VGND='VGND',VPWR='VPWR')
        if (k in seen or not 1<=k<=16 or w[-1]!=BUFFER or dict(zip(defs[BUFFER][0],w[1:-1]))!=expected):
            raise ValueError('Original coarse/tail buffer data/body wiring changed')
        seen.add(k);replacement=w[0]+' '+expected['A']+' '+expected['X']+' VPWR VGND '+component_name(profile)+'\n'
        line=' '.join(w)+'\n'
        if after.count(line)!=1:raise ValueError('Ambiguous coarse buffer source')
        after=after.replace(line,replacement,1)
    if seen!=set(range(1,17)):raise ValueError('Incomplete coarse/tail chain')
    return bank.replace(before,after,1)+'\n'+cell_definition(rc,component_name(profile))


def projection(bank,profile):
    top=name(profile);model=component_name(profile);defs=source.native.definitions(bank)
    block=cell_definition(bank,model)
    if not bank.endswith('\n'+block):raise ValueError('Coarse component definition moved')
    result=bank[:-len('\n'+block)];before=cell_definition(result,top);after=before;seen=set()
    for w in defs[top][1]:
        if w[-1]!=model:continue
        match=re.fullmatch(r'Xdelay(\d+)',w[0]);tail=w[0]=='Xtail_load'
        if match is None and not tail:raise ValueError('Unexpected coarse gang instance')
        k=int(match[1]) if match else 16;pins=dict(zip(defs[model][0],w[1:-1]))
        expected=dict(IN='IN' if k==1 else f'tap{k-1}',OUT=f'tap{k}' if k<16 else 'unused_tail',VPWR='VPWR',VGND='VGND')
        if k in seen or pins!=expected:raise ValueError('Coarse gang data/body wiring changed')
        seen.add(k);old=dict(A=pins['IN'],X=pins['OUT'],VPWR='VPWR',VGND='VGND')
        after=after.replace(' '.join(w)+'\n',w[0]+' '+' '.join(old[p] for p in defs[BUFFER][0])+' '+BUFFER+'\n',1)
    if seen!=set(range(1,17)):raise ValueError('Coarse gang coverage changed')
    return rename(result.replace(before,after,1),top,base.name('w126'))


def transform(text,profile,fine_rc):
    original=base.transform(text,'w126',fine_rc)
    bank=rename(substitute(original,base.name('w126'),profile,checked_coarse(profile)),base.name('w126'),name(profile))
    if projection(bank,profile)!=original:raise ValueError('Unrelated balanced-bank circuitry changed')
    counts=source.primitive_counts(bank,name(profile))
    if sum(v for k,v in counts.items() if 'fet_' in k)!=native_count(profile) or counts.get('sky130_fd_pr__cap_mim_m3_1')!=42:
        raise ValueError('Stronger coarse native inventory changed')
    return bank


def observations(bank,profile,previous):
    result=base.observations(projection(bank,profile),'w126',previous);top=name(profile)
    ports=source.native.definitions(bank)[top][0]
    devices=source.native.mapped_mos(bank,top,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD');byname={d['name']:d for d in devices}
    gates=[dict(g,gate_node=byname[g['device']]['terminals'][1]) for g in result['programming_gates']]
    if len(devices)!=native_count(profile) or len(byname)!=len(devices) or len(gates)!=173:
        raise ValueError('Stronger coarse native/control observations incomplete')
    return dict(result,devices=devices,programming_gates=gates)
