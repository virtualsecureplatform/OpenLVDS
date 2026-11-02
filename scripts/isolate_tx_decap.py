#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Map boundary decaps before MOS-only diagnostic removal; retain every wire R/C."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import numpy as np
from dll_campaign import atomic,text_block
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command,provenance
from spice_library import replace
from reduce_rc import number

ROOT=Path(__file__).resolve().parents[1]
CELL='sky130_fd_sc_hd__decap_3'
TOP='openlvds_tx_core'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def registration(ext,definition):
    """Derive coordinate scale from an independently represented physical pin."""
    port=re.search(r'(?m)^port "tx_serial" \d+ (-?\d+) (-?\d+) (-?\d+) (-?\d+) m3$',ext)
    pin=re.search(r'(?s)- tx_serial \+ NET tx_serial .*?\+ LAYER met3 \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)\s*\+ PLACED \( (-?\d+) (-?\d+) \) N ;',definition)
    units=re.search(r'UNITS DISTANCE MICRONS (\d+) ;',definition)
    if not port or not pin or not units:raise ValueError('Require matching unrotated extraction/DEF pin registration')
    a=list(map(int,port.groups()));b=list(map(int,pin.groups()));rect=[b[0]+b[4],b[1]+b[5],b[2]+b[4],b[3]+b[5]]
    ratios=[y/x for x,y in zip(a,rect) if x]
    if not ratios or max(ratios)-min(ratios)>1e-9:raise ValueError('Physical coordinate registration differs')
    return ratios[0]/int(units[1]),int(units[1])


def mapped_devices(raw,res_ext,definition,lef,cell_spice,registration_ext=None):
    block=text_block(cell_spice,CELL);expected={}
    for line in block.splitlines():
        if line.startswith('X'):
            w=line.split();params=dict(x.split('=') for x in w[6:]);expected[w[5]]=(number(params['w']),number(params['l']))
    targets={'sky130_fd_pr__nfet_01v8':(.55,.59),'sky130_fd_pr__pfet_01v8_hvt':(.87,.59)}
    if set(expected)!=set(targets) or any(not np.allclose(expected[k],targets[k],rtol=0,atol=1e-12) for k in targets):raise ValueError('PDK decap device definition changed')
    expected=targets
    macro=re.search(r'(?ms)^MACRO '+CELL+r'\n.*?^END '+CELL+r'\s*$',lef)
    size=re.search(r'SIZE ([\d.]+) BY ([\d.]+) ;',macro[0]) if macro else None
    if not size:raise ValueError('Missing decap LEF boundary')
    width,height=map(float,size.groups());scale,units=registration(registration_ext if registration_ext is not None else res_ext,definition)
    placed=[]
    for name,x,y,orient in re.findall(r'- (\S+) '+CELL+r' \+ SOURCE DIST \+ FIXED \( (\d+) (\d+) \) (\S+) ;',definition):
        if not name.startswith('PHY_EDGE_ROW_') or orient not in ['N','FN','FS','S']:raise ValueError('Unexpected decap placement')
        placed.append(dict(name=name,x=int(x)/units,y=int(y)/units,orientation=orient))
    if len(placed)!=56 or len({p['name'] for p in placed})!=56:raise ValueError('Require all 56 original boundary cells')
    locations={}
    for line in res_ext.splitlines():
        if not line.startswith('device msubckt '):continue
        w=shlex.split(line)
        if len(w)<15:raise ValueError('Unknown extresist device statement')
        key=(w[2],tuple(sorted([w[11],w[14]])),w[8],w[7])
        locations.setdefault(key,[]).append((float(w[3])*scale,float(w[4])*scale))
    result=[]
    for line in text_block(raw,TOP).splitlines():
        w=line.split()
        if not w or not w[0].startswith('X') or len(w)<8 or w[5] not in expected:continue
        params=dict(v.split('=',1) for v in w[6:] if '=' in v)
        if (number(params['w']),number(params['l']))!=expected[w[5]]:continue
        key=(w[5],tuple(sorted([w[1],w[3]])),w[2],w[4]);points=locations.get(key,[])
        if len(points)!=1:raise ValueError('Decap transistor lacks unique extraction coordinate')
        x,y=points[0];cells=[p for p in placed if p['x']<=x<=p['x']+width and p['y']<=y<=p['y']+height]
        if len(cells)!=1:raise ValueError('Decap transistor lacks unique placed cell')
        n='nfet' in w[5];rail='VGND' if n else 'VPWR';gate='VPWR' if n else 'VGND'
        if not all(v.split('.')[0]==rail for v in [w[1],w[3],w[4]]) or w[2].split('.')[0]!=gate:raise ValueError('Mapped device violates PDK decap rail topology')
        result.append(dict(instance=w[0],cell=cells[0]['name'],model=w[5],coordinate_um=[x,y],statement=line))
    counts=Counter((r['cell'],r['model']) for r in result)
    if len(result)!=112 or any(counts[p['name'],model]!=1 for p in placed for model in expected):raise ValueError('Require both mapped MOS devices in every boundary decap')
    return result


def remove_mapped(raw,mapping):
    lines=raw.splitlines();remove={r['statement'] for r in mapping}
    if len(remove)!=len(mapping) or any(lines.count(line)!=1 for line in remove):raise ValueError('Mapped transistor statements changed')
    result='\n'.join(line for line in lines if line not in remove)+'\n'
    retained=lambda s:[line for line in s.splitlines() if line[:1].upper() in ['R','C']]
    if retained(raw)!=retained(result):raise ValueError('Diagnostic changed extracted R/C')
    return result


def prepare(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/tx_convergence_isolation'):raise ValueError('Use completed TX isolation matrix')
    m=json.loads((parent/'manifest.json').read_text());old=parent/'coupled_raw'
    report=json.loads((old/'summary.json').read_text())
    if report.get('numerically_completed') is not False or not report.get('failure','').startswith('Timestep too small'):raise ValueError('Require terminal raw-RC coupled collapse')
    if report['manifest_sha256']!=sha(parent/'manifest.json'):raise ValueError('Isolation binding changed')
    for n,h in report['files'].items():
        if sha(old/n)!=h:raise ValueError('Original terminal isolation output changed')
    for n,h in m['identity']['inputs'].items():
        if sha(ROOT/n)!=h:raise ValueError('Original extraction inputs changed')
    physical=ROOT/'build/diagnostics/tx_buffer4_physical';info=json.loads((physical/'extraction.json').read_text())
    summary=json.loads((physical/'summary.json').read_text());run=ROOT/summary['run'];raw=ROOT/info['raw_netlist']
    if not summary['passed'] or sha(raw)!=info['reduction']['source_sha256'] or sha(run/'final/gds/openlvds_tx_core.gds')!=info['gds_sha256']:raise ValueError('Physical TX binding changed')
    res=raw.parent/'openlvds_tx_core_rcx.res.ext';ext=raw.parent/'openlvds_tx_core_rcx.ext';definition=run/'final/def/openlvds_tx_core.def'
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd';lef=pdk/'lef/sky130_fd_sc_hd.lef';cell=pdk/'spice/sky130_fd_sc_hd.spice'
    mapping=mapped_devices(raw.read_text(),res.read_text(),definition.read_text(),lef.read_text(),cell.read_text(),ext.read_text())
    base=(old/'library.spice').read_text()
    if text_block(base,TOP)!=text_block(raw.read_text(),TOP):raise ValueError('Raw TX library differs from mapped extraction')
    paths=[parent/'manifest.json',old/'summary.json',old/'bench.cir',old/'library.spice',raw,res,ext,definition,physical/'extraction.json',physical/'summary.json',run/'final/gds/openlvds_tx_core.gds']
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        pdk={str(p):sha(p) for p in [lef,cell]},mapping=mapping,simulator=provenance(),
        code={n:sha(ROOT/'scripts'/n) for n in ['isolate_tx_decap.py','run_ngspice.py','spice_dispatch.py','spice_engine.py','dll_campaign.py','receiver_static_diagnosis.py','spice_library.py','reduce_rc.py']},
        scope='Diagnostic only: remove 112 MOS transistors positively mapped to 56 placed decap boundary cells; retain all raw TX resistors/capacitors and every other device. No physical/circuit/PHY qualification.')
    out=ROOT/'build/diagnostics/tx_decap_isolation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    library=replace(base,TOP,remove_mapped(text_block(raw.read_text(),TOP),mapping))
    deck=(old/'bench.cir').read_text();include=f'.include "{old}/library.spice"'
    if deck.count(include)!=1:raise ValueError('Unexpected coupled inclusion')
    deck=deck.replace(include,f'.include "{out}/library.spice"')
    for n,body in [('library.spice',library),('bench.cir',deck)]:
        p=out/n
        if p.exists() and p.read_text()!=body:raise ValueError('Prepared decap diagnostic changed')
        if not p.exists():p.write_text(body)
    capture_manifest(out/'manifest.json',dict(identity=identity,files={n:sha(out/n) for n in ['library.spice','bench.cir']},qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/tx_decap_isolation'):raise ValueError('Use mapped decap diagnostic')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or any(sha(out/n)!=h for n,h in m['files'].items()):raise ValueError('Mapped diagnostic context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if any((out/n).exists() for n in ['state.json','bench.raw','ngspice.log','summary.json']):raise ValueError('Prior mapped diagnostic output retained')
        atomic(out/'state.json',dict(status='waiting_for_slot',qualified_phy=False))
        with lease(ROOT,priority=2,label='tx_mapped_decap_isolation'):
            unchanged();atomic(out/'state.json',dict(status='running',qualified_phy=False))
            p=subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(p.stdout+p.stderr);unchanged();complete=False
        if p.returncode==0:
            names,w=read_raw(out/'bench.raw');t=w[:,names.index('time')]
            complete=bool(np.isfinite(w).all() and t[0]<=1e-15 and t[-1]>=12e-9-1e-12 and np.all(np.diff(t)>0))
        log=(out/'ngspice.log').read_text();failure=re.search(r'Timestep too small;[^\n]+',log)
        capture_manifest(out/'summary.json',dict(numerically_completed=complete,returncode=p.returncode,failure=failure[0] if failure else None,electrical_verdict=None,qualified_phy=False,manifest_sha256=stamp,
            files={n:sha(out/n) for n in ['bench.raw','ngspice.log','console.log'] if (out/n).exists()},scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_diagnostic',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
