#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remove a restoration pair after the observed native zero-code latency miss."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import probe_pullup_restored_bank_v360 as parent
import analyze_live_bank_history_v364 as history
from spice_dispatch import lease
from spice_engine import engine, provenance

source = parent.source
ROOT = parent.ROOT
PARENT = ROOT/'build/diagnostics/pullup_restored_bank_v360/8dba212d4f9eafd5'
VERSION = 'direct-balanced-taps-recovered-fine-native-bank-v365.1'
CONTEXT = 'direct_balanced_bank_v365'
TOP = 'openlvds_direct_balanced_bank_v365'
sha = parent.sha
atomic = parent.atomic
SCOPE = ('Data-driven paired-inversion removal after observed original zero-code '
         'latency failure: balanced native coarse taps directly drive root TGs '
         'and verified two-P40/N16 fine inverter; no group restorers or pre-driver. '
         'Original four SS40/410MHz eight-event 25ns zero/duty/coarse checks and '
         'quarter/history/period/slew/control/voltage/overlap limits unchanged. '
         '20fF screen only, no next-bank load/new shared RC/dense/update/PVT/DLL/PHY admission')


def specifications():
    return [dict(s, architecture='direct_balanced_taps_recovered_fine',
                 pre_driver='removed_with_group_restorer',
                 regenerator='two_parallel_p40n16_then_final_p20n16') for s in parent.specifications()]


def transform(text, previous):
    defs = source.native.definitions(text)
    ports, body = defs[parent.TOP]
    if (len(previous['devices']) != 2126 or len(previous['controls']) != 86
            or len(previous['programming_gates']) != 266):
        raise ValueError('Require complete original recovered-bank observation maps')
    expected = {'Xfine_pre': ['Xfine_pre', 'selected', 'pre_out', 'VGND', 'VPWR', source.SMALL],
                'Xfine_isolate': ['Xfine_isolate', 'pre_out', 'fine_node', 'VGND', 'VPWR', parent.FINE]}
    for k in range(4):
        expected[f'Xgroup_compound{k}'] = [f'Xgroup_compound{k}', f'tree0_{k}', f'regenerated{k}',
                                         'VPWR', 'VGND', source.GROUP]
        for name in (f'Xswitch1_0_{k}', f'Xroot_parallel{k}'):
            expected[name] = [name, f'regenerated{k}', 'selected', f'en1_{k}', f'en_b1_{k}',
                              'VPWR', 'VGND', source.baseline.source.TG]
    for name, call in expected.items():
        if sum(w == call for w in body) != 1 or sum(w[0] == name for w in body) != 1:
            raise ValueError('Original paired restoration or root/fine topology changed')
    new = []
    for w in body:
        if w[0] == 'Xfine_pre' or w[0].startswith('Xgroup_compound'):
            continue
        w = w.copy()
        if w[0] == 'Xfine_isolate':
            w[1] = 'selected'
        elif w[0].startswith(('Xswitch1_0_', 'Xroot_parallel')):
            w[1] = 'tree0_'+w[0][-1]
        new.append(w)
    if any(token == 'pre_out' or token.startswith('regenerated') for w in new for token in w[1:]):
        raise ValueError('Removed restoration left a dangling top-level signal')
    block = '\n'.join(['.subckt '+TOP+' '+' '.join(ports), *[' '.join(w) for w in new], '.ends '+TOP, ''])
    result = text.replace(source.definition(text, parent.TOP), block, 1)
    if any(source.definition(result, n) != source.definition(text, n) for n in defs if n != parent.TOP):
        raise ValueError('Qualified component definitions changed')
    devices = source.native.mapped_mos(result, TOP,
        {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}, 'XD')
    before = {d['name']: d for d in previous['devices']}
    after = {d['name']: d for d in devices}
    removed = ('XD:Xfine_pre:', *[f'XD:Xgroup_compound{k}:' for k in range(4)])
    changed = ('XD:Xfine_isolate:', *[f'XD:Xswitch1_0_{k}:' for k in range(4)],
               *[f'XD:Xroot_parallel{k}:' for k in range(4)])
    if (len(devices) != 1980 or len(after) != 1980
            or any(n.startswith(removed) for n in after)
            or set(after) != {n for n in before if not n.startswith(removed)}
            or any(after[n] != d for n, d in before.items() if not n.startswith((*removed, *changed)))):
        raise ValueError('Unexpected native inventory or unrelated terminal-map change')
    gates = deepcopy(previous['programming_gates'])
    if any(after[g['device']]['terminals'][1] != g['gate_node'] for g in gates):
        raise ValueError('Original programming gate changed')
    _, leaves = source.inventory.native_leaves(source.collapse(result), TOP)
    if sum('fet_' in d['model'] for d in leaves) != 1980 or sum('cap_mim' in d['model'] for d in leaves) != 130:
        raise ValueError('Actual reachable native MOS/MIM inventory changed')
    return result, dict(devices=devices, controls=deepcopy(previous['controls']), programming_gates=gates)


def fixture(out, identity, spec):
    text = parent.fixture(out, identity, spec)
    if text.count(parent.TOP) != 1 or text.count('.print tran V(XD:pre_out) ') != 1:
        raise ValueError('Original native fixture or explicit pre-stage observation changed')
    return text.replace(parent.TOP, TOP, 1).replace('OpenLVDS '+parent.VERSION, 'OpenLVDS '+VERSION, 1).replace(
        '.print tran V(XD:pre_out) ', '.print tran ', 1)


def evidence(receipt):
    proof = json.loads(receipt.read_text())
    capture = ROOT/proof['original_capture']
    r = json.loads((capture/'summary.json').read_text())
    required = {str((capture/n).relative_to(ROOT)) for n in ('summary.json', *r['files'])}
    if (proof.get('all_captured_bytes_and_crossing_metrics_reproduced') is not True
            or proof.get('source_waveform_complete') is not False or proof.get('qualified_phy') is not False
            or capture != ROOT/'build/reports/live_bank_history_v364/20261107T145500Z'
            or r['process']['raw'] != str((history.PARENT/'0/bench.raw').relative_to(ROOT))
            or proof['original_context_inputs'] != r['inputs']
            or not required <= set(proof['inputs'])
            or proof['native_payload_prefix_sha256'] != r['complete_record_payload_sha256']
            or not np.isfinite(r['prefix_timing']['zero_code_fast_quarter_headroom_ps'])
            or r['prefix_timing']['zero_code_fast_quarter_headroom_ps'] >= 0
            or set(r['stage_histories']) != {'rise', 'fall'}
            or not all(v['all_eight_stage_events_captured'] for v in r['stage_histories'].values())):
        raise ValueError('Require retained original zero-latency failure, not claimed full-run admission')
    inputs = {**proof['inputs'], **r['inputs']}
    for n, h in inputs.items():
        if sha(ROOT/n) != h:
            raise ValueError('Frozen latency evidence changed: '+n)
    with np.load(capture/'selected_native_history.npz', allow_pickle=False) as saved:
        measured = history.histories(saved['data'], r['task']['spec'])
    if any(r[k] != value for k, value in measured.items()):
        raise ValueError('Original captured timing metrics cannot reproduce')
    return {**inputs, str(receipt.relative_to(ROOT)): sha(receipt)}


def prepare(receipt):
    observed = evidence(receipt)
    m = parent.bound(PARENT, full=False)
    i = m['identity']
    text, observations = transform((PARENT/'bank.spice').read_text(), i['observations'])
    paths = [PARENT/'manifest.json', PARENT/'bank.spice']
    paths += sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module, '__file__', None) and Path(module.__file__).resolve().parent == ROOT/'scripts'})
    inputs = {**i['guards'], **observed, **{str(p.relative_to(ROOT)): sha(p) for p in paths}}
    identity = dict(version=VERSION, parent=str(PARENT.relative_to(ROOT)), evidence=str(receipt.relative_to(ROOT)),
        specs=specifications(), model=i['model'], macro_top=TOP, ports=i['ports'], observations=observations,
        inputs=inputs, guards={n: h for n, h in inputs.items() if not n.endswith('.raw')},
        pdk_files=i['pdk_files'], external_files=i['external_files'], simulator=i['simulator'],
        native_revision=dict(native_mos=1980, native_mims=130, controls=86, programming_gates=266,
            path_inversions=2, group_restorers=0, pre_driver=None, coarse_inverter_stages=2,
            fine_driver=parent.FINE, node_polarities=dict(selected='noninverting', fine_node='inverting'),
            unchanged_component_definitions_preserved=True, new_shared_wire_rc_qualified=False),
        max_workers=2, priority=1, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'bank.spice').write_text(text)
    tasks = []
    for k, spec in enumerate(specifications()):
        (out/str(k)).mkdir()
        (out/str(k)/'bench.cir').write_text(fixture(out, identity, spec))
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(out/str(k)/'bench.cir')))
    atomic(out/'manifest.json', dict(identity=identity, tasks=tasks, bank_sha256=sha(out/'bank.spice'), qualified_phy=False))
    return out


def bound(out, full=True):
    m = json.loads((out/'manifest.json').read_text())
    i = m['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION or i['scope'] != SCOPE
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or (i['max_workers'], i['priority']) != (2, 1)
            or i['macro_top'] != TOP or i['model'] not in i['pdk_files']
            or i['guards'] != {n: h for n, h in i['inputs'].items() if not n.endswith('.raw')}
            or engine() != 'ngspice' or provenance() != i['simulator']
            or sha(out/'bank.spice') != m['bank_sha256']):
        raise ValueError('Direct balanced bank identity/runtime changed')
    for n, h in {**(i['inputs'] if full else i['guards']), **i['pdk_files'], **i['external_files']}.items():
        if sha(ROOT/n) != h:
            raise ValueError('Captured native input changed: '+n)
    old = json.loads((PARENT/'manifest.json').read_text())['identity']
    text, observations = transform((PARENT/'bank.spice').read_text(), old['observations'])
    if text != (out/'bank.spice').read_text() or observations != i['observations']:
        raise ValueError('Paired removal or full native map cannot regenerate')
    tasks = []
    for k, spec in enumerate(specifications()):
        if (out/str(k)/'bench.cir').read_text() != fixture(out, i, spec):
            raise ValueError('Full native stimulus/observations changed')
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(out/str(k)/'bench.cir')))
    if tasks != m['tasks']:
        raise ValueError('Original four-point coverage changed')
    return m


def measure(folder, identity, spec):
    return dict(source.measure(folder, identity, spec), scope=SCOPE)


def compare(rows):
    if len(rows)!=4 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['spec'] for r in rows]!=specifications():raise ValueError('Full native bank coverage changed')
    complete=all(len(r['result']['edge_delays_ps'][edge])==8
        and all(np.isfinite(v) and v>0 for v in r['result']['edge_delays_ps'][edge]) for r in rows for edge in ('rise','fall'))
    overlap={edge:min(min(rows[k]['result']['edge_delays_ps'][edge]) for k in (1,2))
        -max(rows[3]['result']['edge_delays_ps'][edge]) if complete else None for edge in ('rise','fall')}
    keys=('current_clock_interface_screen_passed','all_input_output_pulses_present','input_timing_stimulus_passed','full_swing_pulses_passed',
        'unwrapped_native_epoch_passed','pulse_order_and_widths_passed','current_downstream_250ps_slew_domain_passed',
        'period_screen_passed','repeated_delay_screen_passed','zero_code_quarter_passed','terminal_screen_passed',
        'control_settling_passed','periodic_transport_screen_passed')
    return dict(component_hypothesis_passed=bool(complete and all(r['result'].get(k) is True for r in rows for k in keys)
        and all(v>0 for v in overlap.values())),conservative_coarse_overlap_ps=overlap,
        complete_four_point_native_screen=True,shared_wire_rc_qualified=False,all_pvt_covered=False,
        electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial full-bank run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),
                        '-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=measure(folder,i,task['spec'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,spec=task['spec'],result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'campaign'))
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    out = prepare(args.artifact.resolve()) if args.action in ('prepare', 'campaign') else args.artifact.resolve()
    print(out, flush=True)
    if args.action in ('run', 'campaign'):
        print(run(out), flush=True)
