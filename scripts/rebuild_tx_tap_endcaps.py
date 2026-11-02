#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Conditional, isolated TX rebuild with legal tap endcaps and fresh RC audit."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import numpy as np
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from physical_policy import delay_cells_absent,tx_buffered_paths_retained

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_tx_core'
TAP='sky130_fd_sc_hd__tapvpwrvgnd_1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def local(path):
    p=Path(path)
    return ROOT/p.relative_to('/work/OpenLVDS') if p.is_relative_to('/work/OpenLVDS') else p


def inside(path):return '/work/OpenLVDS/'+str(path.relative_to(ROOT))


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,InvocationID,ExecStart'],capture_output=True,text=True,check=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def tap_config(original):
    if original.get('DESIGN_NAME')!=TOP or original.get('DECAP_CELLS')!=[]:raise ValueError('Require original TX config with empty decap fillers')
    result=copy.deepcopy(original)
    result.update(ENDCAP_CELL=TAP,WELLTAP_CELL=TAP,DECAP_CELLS=[])
    return result


def physical_checks(resolved,netlist,powered,definition,metrics):
    config_ok=all(resolved.get(k)==v for k,v in dict(ENDCAP_CELL=TAP,WELLTAP_CELL=TAP,DECAP_CELLS=[]).items())
    devices=re.findall(r'\b(sky130_fd_sc_hd__\w+)\s+(\\?\S+)\s*\((.*?)\);',powered,re.S)
    edge=[];well=[];power=True
    for cell,name,body in devices:
        pins=dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',body))
        power &= pins.get('VPWR')=='VPWR' and pins.get('VGND')=='VGND'
        power &= all(pins.get(k,v)==v for k,v in [('VPB','VPWR'),('VNB','VGND')])
        if name.startswith('PHY_EDGE_'):edge.append((cell,name))
        if name.startswith('TAP_TAPCELL_'):well.append((cell,name))
    def_edges=re.findall(r'- (PHY_EDGE_\S+) (\S+) \+ SOURCE DIST \+ FIXED \( \d+ \d+ \) (N|FN|FS|S) ;',definition)
    boundary=bool(len(edge)==56 and len(def_edges)==56 and len(set(n for _,n in edge))==56 and
        {n for _,n in edge}=={n for n,_,_ in def_edges} and all(c==TAP for c,_ in edge) and all(c==TAP for _,c,_ in def_edges))
    well_ok=bool(well and all(c==TAP for c,_ in well))
    no_decap=bool(devices and not any('__decap_' in c for c,_,_ in devices))
    zero=['magic__drc_error__count','klayout__drc_error__count','design__lvs_error__count',
        'design__disconnected_pin__count','design__critical_disconnected_pin__count','design__power_grid_violation__count']
    physical=all(metrics.get(k)==0 for k in zero)
    sta_keys=[k for k in metrics if re.match(r'^timing__(?:setup|hold)__wns(?:__corner:.*)?$',k)]
    sta=bool(all(k in metrics for k in ['timing__setup__wns','timing__hold__wns']) and len(sta_keys)>=8 and
        all(isinstance(metrics[k],(int,float)) and np.isfinite(metrics[k]) and metrics[k]>=0 for k in sta_keys))
    paths=tx_buffered_paths_retained(netlist,4) and delay_cells_absent(netlist)
    return dict(resolved_taps=config_ok,boundary_cells=boundary,well_taps=well_ok,power_connections=bool(power and devices),
        decap_cells_absent=no_decap,physical_signoff=physical,sta=sta,functional_paths=paths)


def prepare(diagnostic,unit):
    if not diagnostic.is_relative_to(ROOT/'build/diagnostics/tx_decap_isolation'):raise ValueError('Use mapped decap isolation')
    relative=str(diagnostic.relative_to(ROOT));live=owner(unit)
    if live.get('MainPID','0')=='0' or live.get('ActiveState')!='active' or 'scripts/isolate_tx_decap.py run '+relative not in live.get('ExecStart',''):raise ValueError('Require exact live decap producer')
    original=ROOT/'build/diagnostics/tx_buffer4_physical';summary=json.loads((original/'summary.json').read_text())
    from digital_candidate_rc import captured_inputs
    if captured_inputs(original,summary)!=TOP or summary.get('tx_buffer_strength')!=4:raise ValueError('Require original audited buffer4 TX')
    archive=ROOT/summary['input_archive'];config=json.loads((archive/'config.json').read_text());updated=tap_config(config)
    source_paths=[local(p) for p in config['VERILOG_FILES']]+[local(config['EXTRA_VERILOG_MODELS'][0]),local(config['PNR_SDC_FILE'])]
    for p in source_paths:
        if p.read_bytes()!=(archive/p.name).read_bytes():raise ValueError('Original TX source differs from physical archive')
    paths=source_paths+[original/'summary.json',original/'config.json',diagnostic/'manifest.json']
    paths += [archive/p.name for p in source_paths]+[archive/'config.json']
    names=['rebuild_tx_tap_endcaps.py','digital_candidate_rc.py','extract.py','physical_policy.py','lvs_utils.py','audit_rc.py','spice_library.py','run_ngspice.py','receiver_static_diagnosis.py','dll_campaign.py','env.sh']
    identity=dict(diagnostic=relative,unit=unit,owner=live,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code={n:sha(ROOT/'scripts'/n) for n in names},scope='Conditional physical experiment after mapped-MOS removal completes 12 ns. Same TX RTL/constraints, explicit tap endcaps and well taps, no decap fillers. Fresh full flow and RC extraction/audit. No PHY admission.')
    out=ROOT/'build/diagnostics/tx_tap_endcaps'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    # Reuse the exact original source bytes. The archive remains checked before/after flow.
    config_path=out/'config.json'
    body=json.dumps(updated,indent=2)+'\n'
    if config_path.exists() and config_path.read_text()!=body:raise ValueError('Prepared tap config changed')
    if not config_path.exists():config_path.write_text(body)
    capture_manifest(out/'manifest.json',dict(identity=identity,config_sha256=sha(config_path),qualified_phy=False));return out


def unchanged(out,m):
    i=m['identity']
    if out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or sha(out/'config.json')!=m['config_sha256']:raise ValueError('Tap rebuild evidence changed')


def causal_gate(diagnostic,check_pdk=False):
    m=json.loads((diagnostic/'manifest.json').read_text());r=json.loads((diagnostic/'summary.json').read_text())
    if r.get('numerically_completed') is not True or r.get('returncode')!=0 or r.get('manifest_sha256')!=sha(diagnostic/'manifest.json'):return False
    i=m['identity']
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Mapped diagnostic inputs changed')
    if check_pdk:
        from spice_engine import provenance
        if provenance()!=i['simulator'] or any(sha(Path(n))!=h for n,h in i['pdk'].items()):raise ValueError('Mapped diagnostic runtime/PDK changed')
    if len(m['identity']['mapping'])!=112 or any(sha(diagnostic/n)!=h for n,h in dict(m['files'],**r['files']).items()):raise ValueError('Mapped diagnostic proof changed')
    names,w=read_raw(diagnostic/'bench.raw');t=w[:,names.index('time')]
    if not np.isfinite(w).all() or t[0]>1e-15 or t[-1]<12e-9-1e-12 or np.any(np.diff(t)<=0):raise ValueError('Mapped diagnostic trace incomplete')
    return True


def build(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/tx_tap_endcaps'):raise ValueError('Use isolated tap rebuild')
    m=json.loads((out/'manifest.json').read_text());unchanged(out,m)
    if not causal_gate(ROOT/m['identity']['diagnostic'],check_pdk=True):raise ValueError('Mapped decap completion did not support physical experiment')
    with (out/'.build.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'summary.json').exists() or (out/'flow.log').exists():raise ValueError('Prior physical output retained')
        config=json.loads((out/'config.json').read_text());paths=[local(p) for p in config['VERILOG_FILES']]+[local(config['EXTRA_VERILOG_MODELS'][0]),local(config['PNR_SDC_FILE']),out/'config.json']
        stamp=hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest();archive=out/'inputs'/stamp[:16];archive.mkdir(parents=True)
        for p in paths:(archive/p.name).write_bytes(p.read_bytes())
        tag='tap-endcaps-'+stamp[:12]
        args=['python3','-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],'-p','sky130A','-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar','--jobs','2','--run-tag',tag,str(out/'config.json')]
        with (out/'flow.log').open('x') as log:p=subprocess.run(args,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        unchanged(out,m);run=out/'runs'/tag
        metrics=json.loads((run/'final/metrics.json').read_text()) if (run/'final/metrics.json').exists() else {}
        read=lambda path:path.read_text() if path.exists() else ''
        netlist=read(run/'final/nl'/f'{TOP}.nl.v');powered=read(run/'final/pnl'/f'{TOP}.pnl.v');definition=read(run/'final/def'/f'{TOP}.def')
        resolved=json.loads((run/'resolved.json').read_text()) if (run/'resolved.json').exists() else {}
        checks=physical_checks(resolved,netlist,powered,definition,metrics);ok=p.returncode==0 and all(checks.values())
        capture_manifest(out/'summary.json',dict(passed=ok,returncode=p.returncode,run=str(run.relative_to(ROOT)),metrics=metrics,checks=checks,
            source_sha256=stamp,inputs_unchanged=True,delay_cells_absent=delay_cells_absent(netlist),interface_verified=checks['functional_paths'],
            input_archive=str(archive.relative_to(ROOT)),pfd_policy=None,tx_buffer_strength=4,qualified_phy=False))
        if not ok:raise ValueError('Tap-endcap physical signoff held; inspect flow/checks')
        from digital_candidate_rc import run as extract
        if extract(out)!=0:raise ValueError('Fresh tap TX RC audit failed')
        capture_manifest(out/'physical_admission.json',dict(physical_passed=True,rc_audit_passed=True,qualified_phy=False,
            manifest_sha256=sha(out/'manifest.json'),summary_sha256=sha(out/'summary.json'),extraction_sha256=sha(out/'extraction.json'),audit_sha256=sha(out/'rc_audit.json')))


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/tx_tap_endcaps'):raise ValueError('Use prepared tap-endcap handoff')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];unchanged(out,m)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Prior physical handoff retained')
        while True:
            unchanged(out,m);live=owner(i['unit'])
            if live['InvocationID']!=i['owner']['InvocationID']:raise ValueError('Decap producer invocation changed')
            if live['MainPID']=='0':break
            atomic(out/'state.json',dict(status='waiting_for_mapped_decap_result',qualified_phy=False));time.sleep(20)
        diagnostic=ROOT/i['diagnostic']
        if not (diagnostic/'summary.json').exists() or not causal_gate(diagnostic):
            atomic(out/'state.json',dict(status='held_mapped_decap_not_completed',qualified_phy=False));return
        atomic(out/'state.json',dict(status='running_fresh_physical_flow',qualified_phy=False))
        with (out/'build.log').open('x') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','/usr/bin/python3','scripts/rebuild_tx_tap_endcaps.py','build',str(out.relative_to(ROOT))],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        unchanged(out,m);atomic(out/'state.json',dict(status='completed_physical_experiment' if p.returncode==0 else 'held_for_diagnosis',qualified_phy=False))
        p.check_returncode()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','build']);p.add_argument('artifact',type=Path);p.add_argument('--producer-unit');a=p.parse_args()
    if a.action=='prepare':
        if not a.producer_unit:p.error('--producer-unit required')
        print(prepare(a.artifact.resolve(),a.producer_unit),flush=True)
    elif a.action=='run':run(a.artifact.resolve())
    else:build(a.artifact.resolve())
