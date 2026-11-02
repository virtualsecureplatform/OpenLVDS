#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Benchmark witnessed receiver R elimination against both complete native controls."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np
from diagnose_link_clock import pulse_transport
from diagnose_receiver_restoration import diagnose
from dll_campaign import atomic, text_block
from dll_measurements import read_wave
from exact_rc_candidate import parse, static_signature
from receiver_static_diagnosis import capture_manifest
from simulate_link import edge_times
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_library import replace
from spice_probes import ProbeNetwork
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
TOP = 'openlvds_receiver_core'
CASES = ['captured', 'sharp_control']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def complete(wave):
    t = wave[:,1]
    if (len(t) < 2 or not np.isfinite(wave).all() or np.any(np.diff(t) <= 0) or
            t[0] > 1e-15 or t[-1] < 80e-9-1e-12):
        raise ValueError('Require the complete original finite 80 ns receiver trace')


def edges(reference_t, reference_v, candidate_t, candidate_v):
    results = []
    for rising in [False, True]:
        a = edge_times(reference_t, reference_v, .9, rising)
        b = edge_times(candidate_t, candidate_v, .9, rising)
        a = a[(a > 15e-9) & (a < 75e-9)]; b = b[(b > 15e-9) & (b < 75e-9)]
        error = float(np.max(abs(a-b))*1e12) if len(a) == len(b) and len(a) else None
        results.append(dict(rising=rising, reference_count=len(a), candidate_count=len(b), maximum_edge_error_ps=error,
            passed=bool(len(a) == len(b) and (not len(a) or error <= 20))))
    return results


def comparison(a, ah, b, bh):
    complete(a); complete(b)
    if set(ah) != set(bh):
        raise ValueError('Exact receiver benchmark changes printed observations')
    sample = np.linspace(0, 80e-9, 80001)
    voltages = {}
    for name in ah:
        if not name.upper().startswith('V('): continue
        voltages[name] = float(np.max(abs(np.interp(sample,a[:,1],a[:,ah[name]])-np.interp(sample,b[:,1],b[:,bh[name]]))))
    names = ['V(RXCLOCK)', 'V(RXDATA)', 'V(Q0)', 'V(Q1)', 'V(VALID)']
    transitions = {name:edges(a[:,1],a[:,ah[name]],b[:,1],b[:,bh[name]]) for name in names}
    def transport(w,h):
        return pulse_transport(w[:,1],w[:,h['V(RCP)']]-w[:,h['V(RCN)']],w[:,h['V(RXCLOCK)']],15e-9,75e-9)
    ta,tb = transport(a,ah),transport(b,bh)
    signature = lambda r:[(p['polarity'],p['output_edges_in_next_input_period']) for p in r['pulses']]
    same = len(ta['pulses']) == len(tb['pulses']) == 47 and signature(ta) == signature(tb)
    return dict(passed=bool(same and voltages and max(voltages.values()) <= .02 and all(
            row['passed'] for rows in transitions.values() for row in rows)),
        all_printed_voltage_error_v=voltages, digital_crossings=transitions,
        reference_transport=ta, candidate_transport=tb, transport_pattern_preserved=same,
        limits=dict(edge_error_ps=20, voltage_error_v=.02, voltage_sample_step_ps=1),
        scope='All printed voltages over full 0–80 ns without edge exclusions; both edge polarities and original 47-period transport in 15–75 ns. Agreement can preserve a failed receiver and does not establish positive native transport.')


def substitute(source, candidate, signature):
    if static_signature(parse(text_block(source,TOP))) != signature or static_signature(parse(candidate)) != signature:
        raise ValueError('Exact receiver changes a capacitor, device, port or directive')
    result = replace(source,TOP,text_block(candidate,TOP))
    for name in ['lvds_bias','openlvds_ddr_rx']:
        if closure_hash(source,name) != closure_hash(result,name):
            raise ValueError('Exact receiver changes shared bias or digital load')
    return result


def prepare(parent, observation):
    if engine() != 'ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):
        raise ValueError('Use completed native receiver controls with pinned ngspice')
    diagnosis = diagnose(parent)  # Read-only complete evidence validation, even for a failed receiver.
    proof = json.loads((observation/'summary.json').read_text()); candidate = observation/'receiver.exact.spice'
    identity = proof['identity']; layout = ROOT/identity['layout']
    if (not observation.is_relative_to(layout/'exact_reduction_observation') or identity['replay'] != str(parent.relative_to(ROOT)) or
            proof.get('qualified_phy') is not False or proof['witness']['passed'] is not True or sha(candidate) != proof['exact_sha256']):
        raise ValueError('Require this replay\'s bound exact receiver mathematical witness')
    proofs = dict(identity['inputs'], **identity['math_runtime']['binaries'])
    if any(sha(ROOT/n) != h for n,h in proofs.items()):
        raise ValueError('Receiver mathematical witness inputs changed')
    m = json.loads((parent/'manifest.json').read_text())
    paths = [parent/n for n in ['manifest.json','summary.json','library.spice']]
    paths += [parent/c/n for c in CASES for n in ['summary.json','bench.cir','bench.cir.prn','ngspice.log']]
    paths += [observation/n for n in ['summary.json','receiver.exact.spice']]+[diagnosis/'summary.json']
    code = set(m['identity']['code']) | {Path(__file__).name,'exact_rc_candidate.py','observe_receiver_exact_rc.py',
        'diagnose_receiver_restoration.py','spice_dispatch.py','spice_library.py','spice_probes.py','spice_scope.py'}
    inputs = dict(proofs, **{str(p.relative_to(ROOT)):sha(p) for p in paths})
    i = dict(parent=str(parent.relative_to(ROOT)), observation=str(observation.relative_to(ROOT)), inputs=inputs,
        code={n:sha(ROOT/'scripts'/n) for n in sorted(code)}, simulator_provenance=provenance(),
        priority=2, workers=1, no_outer_lease=True,
        scope='Original complete 80 ns captured/sharp native fixtures and 1 ps maximum step. Only independently witnessed resistor-only algebraic elimination; all devices/capacitors/ports/probes retained. No active-model, catalog, component, native-transport or PHY promotion. Runtime observations are workload dependent.')
    out = ROOT/'build/diagnostics/receiver_exact_benchmark'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    library = substitute((parent/'library.spice').read_text(),candidate.read_text(),proof['non_resistor_sha256'])
    def store(p,text):
        if p.exists() and p.read_text() != text: raise ValueError('Prepared exact receiver benchmark changed')
        if not p.exists(): p.write_text(text)
    store(out/'library.spice',library); tasks = []
    for case in CASES:
        old = parent/case; folder = out/case; folder.mkdir(exist_ok=True)
        deck = (old/'bench.cir').read_text(); include = f'.include "{parent}/library.spice"'
        if deck.count(include) != 1: raise ValueError('Unexpected original receiver inclusion')
        deck = deck.replace(include,f'.include "{out}/library.spice"')
        printed = re.findall(r'(?im)^\.print tran[^\n]*$',deck)
        if len(printed) != 1: raise ValueError('Require unchanged original receiver observations')
        ProbeNetwork(library).validate(deck,re.findall(r'V\(([^)]+)\)',printed[0],re.I))
        store(folder/'bench.cir',deck); tasks.append(dict(id=case,deck_sha256=sha(folder/'bench.cir')))
    capture_manifest(out/'manifest.json',dict(identity=i,tasks=tasks,library_sha256=sha(out/'library.spice'),qualified_phy=False))
    return out


def elapsed(log):
    values = re.findall(r'Total elapsed time \(seconds\)\s*=\s*([0-9.eE+-]+)',log)
    if len(values) != 1 or not np.isfinite(float(values[0])) or float(values[0]) <= 0:
        raise ValueError('Missing complete positive ngspice runtime observation')
    return float(values[0])


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_exact_benchmark'):
        raise ValueError('Use a prepared exact receiver benchmark')
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']; stamp = sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                i.get('priority') != 2 or i.get('workers') != 1 or i.get('no_outer_lease') is not True or
                [t['id'] for t in m['tasks']] != CASES or sha(out/'library.spice') != m['library_sha256'] or
                any(sha(ROOT/n) != h for n,h in i['inputs'].items()) or
                any(sha(ROOT/'scripts'/n) != h for n,h in i['code'].items()) or
                any(sha(out/t['id']/'bench.cir') != t['deck_sha256'] for t in m['tasks'])):
            raise ValueError('Exact receiver benchmark context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        try:
            for task in m['tasks']:
                folder = out/task['id']; prior = ROOT/i['parent']/task['id']
                cached = json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
                if cached is None:
                    if any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):
                        raise ValueError('Partial exact receiver output retained; use a fresh context')
                    atomic(out/'state.json',dict(status='waiting_for_slot',task=task['id'],qualified_phy=False))
                    with lease(ROOT,priority=2,label='exact-receiver-'+task['id']):
                        unchanged(); atomic(out/'state.json',dict(status='running',task=task['id'],qualified_phy=False))
                        started = time.monotonic()
                        p = subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                        atomic(folder/'runtime.json',dict(wall_seconds=time.monotonic()-started))
                    (folder/'console.log').write_text(p.stdout+p.stderr); p.check_returncode()
                elif sha(folder/'bench.cir.prn') != cached['waveform_sha256']:
                    raise ValueError('Completed exact receiver trace changed')
                unchanged(); agree = comparison(*read_wave(prior/'bench.cir.prn'),*read_wave(folder/'bench.cir.prn'))
                r = dict(task=task['id'],passed=agree['passed'],manifest_sha256=stamp,qualified_phy=False,
                    waveform_sha256=sha(folder/'bench.cir.prn'),reference_waveform_sha256=sha(prior/'bench.cir.prn'),
                    comparison=agree,reference_simulator_seconds=elapsed((prior/'ngspice.log').read_text()),
                    candidate_simulator_seconds=elapsed((folder/'ngspice.log').read_text()))
                if cached is not None and cached != r: raise ValueError('Exact receiver comparison remeasurement changed')
                unchanged();capture_manifest(folder/'summary.json',r);results.append(r)
            capture_manifest(out/'summary.json',dict(diagnostic_complete=True,passed=all(r['passed'] for r in results),
                qualified_phy=False,manifest_sha256=stamp,results=results,scope=i['scope']))
            atomic(out/'state.json',dict(status='completed',passed=all(r['passed'] for r in results),qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(error),qualified_phy=False));raise


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('parent',type=Path);a.add_argument('observation',type=Path)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.parent.resolve(),a.observation.resolve()),flush=True)
    else:run(a.artifact.resolve())
