#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure the five changed thin-device terminal voltages from completed source traces."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re

import numpy as np
from dll_measurements import read_wave
from layout import circuits
from qualify_receiver_components import rebind
import receiver_scaled_decision_experiment as source
from receiver_static_diagnosis import capture_manifest
from receiver_scaled_decision_matrix import selected_cases
from spice_engine import provenance

ROOT=Path(__file__).resolve().parents[1]
DEVICES=['XCT','XC0','XC1','XCD','XCM']
THIN_GUARD_V=1.95  # Same project screening guard as ota_operating_points.py.


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def terminal_metrics(wave,headers,rows):
    measured=source.measured(wave,headers,True)
    values={'VSS':np.zeros(len(wave)),'VDDD':np.full(len(wave),1.8)}
    def voltage(node):
        if node not in values:
            key='V(XR:XCORE:'+node.upper()+')'
            if key not in headers:raise ValueError('Missing decision terminal observation: '+node)
            values[node]=wave[:,headers[key]]
        return values[node]
    result={}
    for name in DEVICES:
        row=rows[name];nodes=row[1]
        if len(nodes)!=4 or not re.fullmatch(r'sky130_fd_pr__(?:n|p)fet_01v8',row[2]):
            raise ValueError('Expected the five declared thin decision devices')
        terminals=[voltage(n) for n in nodes]
        peaks=[]
        for a,b in itertools.combinations(range(4),2):
            delta=abs(terminals[a]-terminals[b]);index=int(np.argmax(delta))
            peaks.append(dict(terminal_pair=['DGSB'[a],'DGSB'[b]],voltage_v=float(delta[index]),time_ns=float(wave[index,1]*1e9)))
        peak=max(peaks,key=lambda p:p['voltage_v'])
        sampled=np.interp(np.arange(12)*12e-9+10e-9,wave[:,1],terminals[0]-terminals[2])
        result[name]=dict(model=row[2],nodes=nodes,params=row[3],maximum_terminal_difference=peak,
            thin_guard_passed=peak['voltage_v']<=THIN_GUARD_V,
            settled_min_abs_vds_v=float(np.min(abs(sampled))),settled_max_abs_vds_v=float(np.max(abs(sampled))))
    return dict(logic_passed=measured['metrics']['passed'],devices=result)


def analyze(matrix):
    if not matrix.is_relative_to(ROOT/'build/diagnostics/receiver_scaled_decision_matrix'):
        raise ValueError('Use the uniformly scaled receiver source DC matrix')
    manifest=json.loads((matrix/'manifest.json').read_text());identity=manifest['identity']
    if len(identity['children'])!=15 or identity['requirements_sha256']!=digest(ROOT/'requirements.json'):
        raise ValueError('Source DC coverage or requirements changed')
    children=selected_cases(manifest,json.loads((ROOT/'requirements.json').read_text()))
    if (identity['producer_sha256']!=digest(ROOT/'scripts/receiver_scaled_decision_matrix.py') or
            any(digest(ROOT/'scripts'/n)!=sha for n,sha in identity['code'].items())):
        raise ValueError('Source DC matrix producer changed')
    proofs={str((matrix/'manifest.json').relative_to(ROOT)):digest(matrix/'manifest.json')}
    results=[]
    for child in children:
        folder=(ROOT/child['root']).resolve()
        if not folder.is_relative_to(ROOT/'build/diagnostics/receiver_scaled_decision_static'):
            raise ValueError('Unexpected decision source context')
        if not (folder/'summary.json').exists():continue
        local=json.loads((folder/'manifest.json').read_text());case=json.loads((folder/'summary.json').read_text())
        if (digest(folder/'manifest.json')!=child['manifest_sha256'] or case.get('diagnostic_complete') is not True or
                case['manifest_sha256']!=child['manifest_sha256'] or case['waveform_sha256']!=digest(folder/'bench.cir.prn')):
            raise ValueError('Completed source trace binding changed')
        context=local['identity']
        if (provenance()!=context['simulator_provenance'] or
                any(digest(ROOT/'scripts'/n)!=sha for n,sha in context['code'].items()) or
                any(digest(ROOT/n)!=sha for n,sha in context['inputs'].items()) or
                any(digest(folder/n)!=sha for n,sha in local['files'].items())):
            raise ValueError('Source context changed')
        parent=ROOT/context['parent']
        if ((folder/'source.spice').read_text()!=source.scale_decision((parent/'source.spice').read_text()) or
                (folder/'bench.cir').read_text()!=rebind((parent/'bench.cir').read_text(),parent,folder)):
            raise ValueError('Source differs from the declared five-width intervention')
        deck=(folder/'bench.cir').read_text()
        if not re.search(r'(?m)^VDIG VDDD 0 1\.8\s*$',deck) or not re.search(r'(?m)^VIO VDDIO 0 3\.3\s*$',deck):
            raise ValueError('Expected the original fixed source rails')
        wave,headers=read_wave(folder/'bench.cir.prn')
        measured=source.measured(wave,headers,True)
        if measured!=case['scaled_decision']:raise ValueError('Saved source analysis differs from actual waveform')
        rows={r[0]:r for r in circuits((folder/'source.spice').read_text())[source.TOP][1]}
        result=terminal_metrics(wave,headers,rows);results.append(dict(case=child['case'],**result))
        for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn']:
            proofs[str((folder/n).relative_to(ROOT))]=digest(folder/n)
    if not results:raise ValueError('No completed source traces to observe')
    capture=dict(producer_sha256=digest(Path(__file__)),proofs=proofs,thin_guard_v=THIN_GUARD_V)
    key=hashlib.sha256(json.dumps(capture,sort_keys=True).encode()).hexdigest()[:16]
    out=matrix/'decision_headroom'/key;out.mkdir(parents=True,exist_ok=True);capture_manifest(out/'manifest.json',capture)
    if any(digest(ROOT/n)!=sha for n,sha in proofs.items()):raise ValueError('Source evidence changed during analysis')
    report=dict(qualified_phy=False,required_cases=15,observed_cases=len(results),all_cases_observed=len(results)==15,
        thin_guard_v=THIN_GUARD_V,observed_thin_guard_passed=all(d['thin_guard_passed'] for r in results for d in r['devices'].values()),
        supply_current_and_power_measured=False,saturation_regions_measured=False,results=results,
        scope='Five changed schematic decision devices only; full original 144 ns traces for completed cases. Excludes other receiver devices, native RC, power and transistor-region qualification.')
    capture_manifest(out/'summary.json',report);print(out/'summary.json',flush=True)
    return out,report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('matrix',type=Path);args=parser.parse_args()
    analyze(args.matrix.resolve())
