#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rebuild both original digital endpoints with tap endcaps after causal isolation."""
import argparse
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import numpy as np
import rebuild_tx_tap_endcaps as tx
import digital_candidate_rc as tx_rc
import rx_candidate_rc as rx_rc
from rx_buffered_policy import retained,policy_parameters
from receiver_static_diagnosis import capture_manifest
from dll_campaign import atomic
from run_ngspice import read_raw
from spice_engine import provenance

ROOT=Path(__file__).resolve().parents[1]
DESIGNS=dict(tx='openlvds_tx_core',rx='openlvds_ddr_rx')
CODE=['rebuild_endpoint_tap_cells.py','rebuild_tx_tap_endcaps.py','digital_candidate_rc.py',
      'rx_candidate_rc.py','rx_buffered_policy.py','physical_policy.py','extract.py','audit_rc.py',
      'lvs_utils.py','spice_library.py','run_ngspice.py','spice_engine.py','receiver_static_diagnosis.py','dll_campaign.py','env.sh']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def tap_config(config):
    if config.get('DESIGN_NAME') not in DESIGNS.values() or config.get('DECAP_CELLS')!=[]:raise ValueError('Use original endpoint configuration')
    result=copy.deepcopy(config);result.update(ENDCAP_CELL=tx.TAP,WELLTAP_CELL=tx.TAP,DECAP_CELLS=[])
    return result


def causal_gate(matrix,check_runtime=False):
    if not matrix.is_relative_to(ROOT/'build/diagnostics/endpoint_decap_isolation'):raise ValueError('Use mapped endpoint isolation matrix')
    m=json.loads((matrix/'manifest.json').read_text());i=m['identity']
    task=next(t for t in m['tasks'] if t['id']=='both_endpoints');folder=matrix/task['id']
    r=json.loads((folder/'summary.json').read_text())
    if r.get('numerically_completed') is not True or r.get('returncode')!=0 or r.get('manifest_sha256')!=sha(matrix/'manifest.json'):raise ValueError('Both-endpoint MOS removal must complete the full twelve ns before physical rebuilding')
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Endpoint isolation source/producer changed')
    if check_runtime and (provenance()!=i['simulator'] or any(sha(Path(n))!=h for n,h in i['pdk'].items())):raise ValueError('Endpoint isolation runtime/PDK changed')
    if len(i['mapping'])!=112 or any(sha(folder/n)!=h for n,h in dict(task['files'],**r['files']).items()):raise ValueError('Endpoint isolation receipt changed')
    names,w=read_raw(folder/'bench.raw');t=w[:,names.index('time')]
    if not np.isfinite(w).all() or t[0]>1e-15 or t[-1]<12e-9-1e-12 or np.any(np.diff(t)<=0):raise ValueError('Endpoint isolation trace incomplete')
    return [matrix/'manifest.json',folder/'summary.json',folder/'bench.raw',folder/'ngspice.log',folder/'bench.cir',folder/'library.spice']


@contextmanager
def physical_policy(kind,rx_policy):
    previous=tx.tx_buffered_paths_retained
    try:
        if kind=='rx':tx.tx_buffered_paths_retained=lambda netlist,strength:retained(netlist,**policy_parameters(rx_policy))
        yield
    finally:tx.tx_buffered_paths_retained=previous


def prepare(matrix):
    paths=causal_gate(matrix)
    originals=dict(tx=ROOT/'build/diagnostics/tx_buffer4_physical',rx=ROOT/'build/diagnostics/rx_early_physical_v1')
    configs={};source_inputs={};rx_policy=None;code=set(CODE)
    for kind,original in originals.items():
        s=json.loads((original/'summary.json').read_text())
        if kind=='tx':
            if tx_rc.captured_inputs(original,s)!=DESIGNS[kind] or s.get('tx_buffer_strength')!=4:raise ValueError('Require original buffer4 TX')
        else:
            rx_rc.captured_inputs(original);rx_policy=s['rx_policy']
            old_identity=json.loads((original/'identity.json').read_text());code.update(old_identity['producer_code'])
            paths += [original/'identity.json']
        archive=ROOT/s['input_archive'];config=json.loads((original/'config.json').read_text())
        files=[tx.local(p) for p in config['VERILOG_FILES']]+[tx.local(config['EXTRA_VERILOG_MODELS'][0]),tx.local(config['PNR_SDC_FILE'])]
        if any(p.read_bytes()!=(archive/p.name).read_bytes() for p in files):raise ValueError('Original endpoint source differs from its physical archive')
        paths += files+[archive/p.name for p in files]+[original/'summary.json',original/'config.json',archive/'config.json']
        configs[kind]=tap_config(config);source_inputs[kind]=[str(p.relative_to(ROOT)) for p in files]
    identity=dict(matrix=str(matrix.relative_to(ROOT)),originals={k:str(v.relative_to(ROOT)) for k,v in originals.items()},
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},source_inputs=source_inputs,rx_policy=rx_policy,
        code={n:sha(ROOT/'scripts'/n) for n in sorted(code)},flow_jobs=2,
        scope='Fresh sequential TX/RX physical experiments. Preserve original RTL, constraints and flow configuration except tap endcaps/well taps and empty decap fillers. Require physical checks and fresh extracted RC audits. No PHY or electrical admission.')
    out=ROOT/'build/diagnostics/endpoint_tap_physical'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    files={}
    for kind,config in configs.items():
        folder=out/kind;folder.mkdir(exist_ok=True);p=folder/'config.json';body=json.dumps(config,indent=2)+'\n'
        if p.exists() and p.read_text()!=body:raise ValueError('Prepared endpoint physical configuration changed')
        if not p.exists():p.write_text(body)
        files[kind+'/config.json']=sha(p)
    capture_manifest(out/'manifest.json',dict(identity=identity,files=files,qualified_phy=False));return out


def unchanged(out,m):
    i=m['identity']
    if out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or i['flow_jobs']!=2 or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or any(sha(out/n)!=h for n,h in m['files'].items()):raise ValueError('Endpoint physical experiment changed')


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/endpoint_tap_physical'):raise ValueError('Use isolated endpoint physical context')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];unchanged(out,m);causal_gate(ROOT/i['matrix'],check_runtime=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Prior endpoint physical output retained')
        results=[]
        for kind,name in DESIGNS.items():
            folder=out/kind;config=json.loads((folder/'config.json').read_text());paths=[ROOT/n for n in i['source_inputs'][kind]]+[folder/'config.json']
            hashes={p.name:sha(p) for p in paths}
            if len(hashes)!=len(paths):raise ValueError('Duplicate physical input basename')
            stamp=(hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest() if kind=='tx' else
                   hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest())
            archive=folder/'inputs'/stamp[:16];archive.mkdir(parents=True)
            for p in paths:(archive/p.name).write_bytes(p.read_bytes())
            if kind=='rx':
                producers=folder/'producers';producers.mkdir()
                for n in i['code']:(producers/n).write_bytes((ROOT/'scripts'/n).read_bytes())
                capture_manifest(folder/'identity.json',dict(inputs=hashes,producer_code=i['code'],rx_policy=i['rx_policy']))
            tag=kind+'-tap-endcaps-'+stamp[:12]
            atomic(out/'state.json',dict(status='running_'+kind+'_physical',qualified_phy=False))
            args=['python3','-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],'-p','sky130A','-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar','--jobs','2','--run-tag',tag,str(folder/'config.json')]
            with (folder/'flow.log').open('x') as log:p=subprocess.run(args,cwd=folder,stdout=log,stderr=subprocess.STDOUT)
            unchanged(out,m);flow=folder/'runs'/tag
            read=lambda path:path.read_text() if path.exists() else ''
            metrics=json.loads((flow/'final/metrics.json').read_text()) if (flow/'final/metrics.json').exists() else {}
            resolved=json.loads((flow/'resolved.json').read_text()) if (flow/'resolved.json').exists() else {}
            nl=read(flow/'final/nl'/f'{name}.nl.v');pnl=read(flow/'final/pnl'/f'{name}.pnl.v');definition=read(flow/'final/def'/f'{name}.def')
            with physical_policy(kind,i['rx_policy']):checks=tx.physical_checks(resolved,nl,pnl,definition,metrics)
            ok=p.returncode==0 and all(checks.values())
            report=dict(passed=ok,returncode=p.returncode,run=str(flow.relative_to(ROOT)),metrics=metrics,checks=checks,
                source_sha256=stamp,inputs_unchanged=True,interface_verified=checks['functional_paths'],delay_cells_absent=tx.delay_cells_absent(nl),
                input_archive=str(archive.relative_to(ROOT)),qualified_phy=False)
            if kind=='tx':report.update(tx_buffer_strength=4,pfd_policy=None)
            else:report.update(rx_policy=i['rx_policy'])
            capture_manifest(folder/'summary.json',report)
            if not ok:
                atomic(out/'state.json',dict(status='held_'+kind+'_physical_checks',qualified_phy=False));raise ValueError('Endpoint physical checks failed; retain output')
            atomic(out/'state.json',dict(status='extracting_'+kind+'_rc',qualified_phy=False))
            if (tx_rc.run(folder) if kind=='tx' else rx_rc.run(folder))!=0:raise ValueError('Endpoint fresh RC audit failed')
            results.append(dict(kind=kind,physical_passed=True,rc_audit_passed=True,
                files={n:sha(folder/n) for n in ['summary.json','extraction.json','rc_audit.json']}))
        unchanged(out,m)
        capture_manifest(out/'summary.json',dict(results=results,physical_experiment_passed=True,manifest_sha256=sha(out/'manifest.json'),qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_physical_experiment',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
