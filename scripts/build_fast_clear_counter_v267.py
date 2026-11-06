#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Strengthen the two high-phase setters after measured stopped-high clear failure."""
import argparse
from collections import Counter
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import build_strong_storage_counter_v234 as source
import native_bank_inventory_v51 as inventory
from probe_digital_dcc_v2 import atomic

ROOT=source.ROOT
NAME=source.NAME
PORTS=source.PORTS
sha=source.sha
VERSION='strong-storage-native-nand8-high-phase-setters-physical-v267.1'
CONTEXT='fast_clear_counter_physical_v267'
OLD='openlvds_nand2_4_o3_shunted_v2'
NEW='openlvds_nand2_8_shunted_v2'
SETTERS={'high1_set','high2_set'}
SCOPE='Existing 22-macro strong-storage counter with only two high-phase setters changed to qualified native NAND8, same phase logic and reset protocol; physical candidate only, no RC/timing/PVT/PHY admission'


def changed_cells(cells):
    if len(cells)!=22 or len({c['name'] for c in cells})!=22:raise ValueError('Require original 22-macro stronger-storage counter')
    selected=[c for c in cells if c['name'] in SETTERS]
    if len(selected)!=2 or any(c['model']!=OLD for c in selected):raise ValueError('Original high-phase setter models changed')
    result=deepcopy(cells)
    for cell in result:
        if cell['name'] in SETTERS:cell['model']=NEW
    return result


def census(cells,macros):
    text=source.original.source(cells,macros)
    ports,leaves=inventory.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',text),NAME)
    if ports!=PORTS:raise ValueError('Counter candidate public ports changed')
    return dict(native_model_counts=dict(Counter(d['model'] for d in leaves)),native_primitives=len(leaves))


def require_diagnosis(folder):
    m=json.loads((folder/'manifest.json').read_text());i=m['identity'];r=json.loads((folder/'summary.json').read_text())
    if (folder.parent!=ROOT/'build/diagnostics/strong_counter_clear_diagnosis_v266'
        or i['version']!='completed-strong-counter-native-stopped-clear-diagnosis-v266.1'
        or folder.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or r.get('analysis_completed') is not True or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):
        raise ValueError('Require exact complete native strong-counter clear diagnosis')
    failures=[row for row in r['rows'] if row['task']['spec']['stop_level']==1
        and row['task']['spec']['process']=='ss' and row['task']['spec']['temperature']==0
        and row['task']['spec']['duty']==.5 and row['task']['spec']['mhz']==410]
    if len(failures)!=1:raise ValueError('Require explicit completed cold stopped-high reference')
    row=failures[0];g=row['recorded_gates'];clear=row['clear'];prep=clear['outputs']['PREPARE'];release=clear['outputs']['RESET_N']
    if (row.get('original_metrics_reproduced') is not True or row.get('native_mos_observed')!=612
        or row.get('terminal_screen_passed') is not True or g.get('stopped_clock_clear_and_reassert_passed') is not False
        or clear.get('original_async_clear_gate_reproduced') is not False
        or prep.get('external_reassert_headroom_ps') is None or prep['external_reassert_headroom_ps']>=0
        or release.get('clear_before_external_reassert_passed') is not True
        or any(g.get(k) is not True for k in ('held_before_request_passed','phase_arming_passed','stopped_clock_arm_clear_passed',
                  'alternating_phase_order_passed','stopped_clock_intermediate_clear_passed'))):
        raise ValueError('Require isolated PREPARE late-clear failure with passing startup/native safety')
    return i,r


def prepare(parent,diagnosis):
    di,dr=require_diagnosis(diagnosis);m=source.bound(parent);i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or r.get('compact_counter_physical_passed') is not True or any(sha(parent/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged qualified original strong-storage physical counter')
    for row in dr['rows']:
        pilot=ROOT/row['case'];pi=json.loads((pilot.parent/'manifest.json').read_text())['identity']
        ri=json.loads((ROOT/pi['parent']/'manifest.json').read_text())['identity']
        if ri['parent']!=str(parent.relative_to(ROOT)):raise ValueError('Clear diagnosis belongs to another physical counter')
    cells=changed_cells(i['cells']);macros=deepcopy(i['macros'])
    if NEW not in macros:raise ValueError('Require already qualified native NAND8 setter master')
    plan=source.strong_plan(cells,macros,source.original.default_plan())
    native_census=census(cells,macros);witness=source.native_master_witness(macros)
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]
    paths += [diagnosis/n for n in ('manifest.json','summary.json','state.json')]
    paths += [ROOT/n for n in {*i['inputs'],*di['inputs']}]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(i,version=VERSION,parent=str(parent.relative_to(ROOT)),diagnosis=str(diagnosis.relative_to(ROOT)),
        cells=cells,macros=macros,**plan,native_census=native_census,native_master_witness=witness,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or source.native.environment.tools()!=i['tools'] or sha(Path(source.original.repaired.CAD))!=i['cad']['sha256']):
        raise ValueError('Fast-clear native physical candidate context changed')
    original=json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity']
    if i['cells']!=changed_cells(original['cells']) or i['macros']!=original['macros'] or i['native_census']!=census(i['cells'],i['macros']):
        raise ValueError('Fast-clear candidate changed unrelated native topology or masters')
    expected=source.strong_plan(i['cells'],i['macros'],source.original.default_plan())
    if any(i[k]!=expected[k] for k in expected):raise ValueError('Fast-clear native placement/routing cannot regenerate')
    return m


def run(out):
    i=bound(out)['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial fast-clear geometry')
        atomic(out/'state.json',dict(status='routing',qualified_phy=False));folder=out/NAME;folder.mkdir()
        try:
            physical=source.draw(folder,i);atomic(folder/'summary.json',physical);bound(out)
            result=dict(physical=physical,passed=physical['passed'],same_phase_logic=True,high_phase_setters_strengthened=sorted(SETTERS),
                native_census=i['native_census'],fast_clear_counter_physical_passed=physical['passed'],
                shared_wire_rc_qualified=False,counter_timing_qualified=False,qualified_phy=False,scope=SCOPE)
            result['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
            atomic(out/'summary.json',result);atomic(out/'state.json',dict(status='complete',passed=physical['passed'],qualified_phy=False));return out
        except Exception as e:atomic(out/'state.json',dict(status='failed',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--diagnosis',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.diagnosis is None:p.error('--diagnosis required')
        out=prepare(out,a.diagnosis.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
