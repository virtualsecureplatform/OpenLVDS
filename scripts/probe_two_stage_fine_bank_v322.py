#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test a direct two-level TG mux and two regular fine/output inverters."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import probe_regular_regenerated_bank_v263 as source
from audit_rc_comments_v2 import collapse
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT = source.ROOT
sha = source.sha
VERSION = 'direct-two-level-tg-and-two-inverter-isolated-fine-native-pilot-v322.1'
CONTEXT = 'two_stage_fine_bank_v322'
TOP = 'openlvds_two_stage_fine_v322'
TG = 'openlvds_tg_quad_stacked_nlvt_v27'
GROUP = 'openlvds_parallel_inv8_v110'
REMOVED = tuple('XD:Xgroup_compound'+str(k)+':' for k in range(4))+('XD:Xfine_regenerate0:',)
REWIRED = tuple('XD:Xswitch1_0_'+str(k)+':' for k in range(4))+tuple(
    'XD:Xroot_parallel'+str(k)+':' for k in range(4))+('XD:Xfine_regenerate1:',)
SCOPE = ('Direct original two-level parallel-root TG mux -> original loaded P20/N16 fine '
         'inverter -> original final P20/N16; group regeneration and one output inversion '
         'removed together, fine cells/coarse/controls unchanged; qualified component RC '
         'with ideal new shared wires, no whole-bank/dense/update/PVT/DLL/PHY admission')


def specifications():
    return [dict(s, architecture='direct_two_tg_levels_two_inverters') for s in source.specifications()]


def transform(bank, previous):
    definitions = source.native.definitions(bank)
    body = definitions[source.TOP][1]
    before = source.cell_definition(bank, source.TOP)
    after = before
    for k in range(4):
        group = [f'Xgroup_compound{k}', f'tree0_{k}', f'regenerated{k}', 'VPWR', 'VGND', GROUP]
        if [w for w in body if w[0] == group[0]] != [group]:
            raise ValueError('Original group restoration topology changed')
        after = after.replace(' '.join(group)+'\n', '', 1)
        for tag in (f'Xswitch1_0_{k}', f'Xroot_parallel{k}'):
            old = [tag, f'regenerated{k}', 'selected', f'en1_{k}', f'en_b1_{k}', 'VPWR', 'VGND', TG]
            if [w for w in body if w[0] == tag] != [old]:
                raise ValueError('Original parallel-root TG wiring or controls changed')
            after = after.replace(' '.join(old)+'\n', ' '.join([tag, f'tree0_{k}', *old[2:]])+'\n', 1)
    isolate = ['Xfine_isolate', 'selected', 'fine_node', 'VGND', 'VPWR', source.MODEL]
    removed = ['Xfine_regenerate0', 'fine_node', 'restored_b', 'VGND', 'VPWR', source.MODEL]
    final = ['Xfine_regenerate1', 'restored_b', 'OUT', 'VGND', 'VPWR', source.MODEL]
    for row in (isolate, removed, final):
        if [w for w in body if w[0] == row[0]] != [row]:
            raise ValueError('Original isolated three-inverter path changed')
    after = after.replace(' '.join(removed)+'\n', '', 1)
    after = after.replace(' '.join(final)+'\n', ' '.join([final[0], 'fine_node', *final[2:]])+'\n', 1)
    after = after.replace('.subckt '+source.TOP+' ', '.subckt '+TOP+' ', 1)
    after = after.replace('.ends '+source.TOP+'\n', '.ends '+TOP+'\n', 1)
    result = bank.replace(before, after, 1)
    top = source.native.definitions(result)[TOP][1]
    if any(w[0].startswith('Xgroup_compound') or 'restored_b' in w
           or any(re.fullmatch(r'regenerated[0-3]', n) for n in w) for w in top):
        raise ValueError('Removed restoration outputs remain referenced')
    for name in definitions:
        if name != source.TOP and source.cell_definition(result, name) != source.cell_definition(bank, name):
            raise ValueError('Unrelated qualified component definition changed')
    ports = definitions[source.TOP][0]
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = source.native.mapped_mos(result, TOP, pins, 'XD')
    old = {d['name']: d for d in previous['devices']}
    new = {d['name']: d for d in devices}
    if (len(old) != 1529 or len(new) != len(devices) or len(new) != 1365
            or sum(n.startswith(REMOVED) for n in old) != 164
            or set(old)-set(new) != {n for n in old if n.startswith(REMOVED)}
            or any(new[n] != d for n, d in old.items() if not n.startswith(REMOVED+REWIRED))):
        raise ValueError('Unexpected removed MOS or unrelated native terminal-map change')
    gates = [dict(g, gate_node=new[g['device']]['terminals'][1]) for g in previous['programming_gates']]
    if gates != previous['programming_gates'] or len(gates) != 173 or len(previous['controls']) != 86:
        raise ValueError('Original typed programming or logical control coverage changed')
    _, leaves = source.inventory.native_leaves(collapse(result), TOP)
    if (sum('fet_' in d['model'] for d in leaves) != 1365
            or sum('cap_mim' in d['model'] for d in leaves) != 34 or len(leaves) != 1399):
        raise ValueError('Native two-stage 1365-MOS/34-MIM inventory changed')
    observations = dict(devices=devices, controls=previous['controls'], programming_gates=gates)
    revision = dict(native_mos=1365, native_mims=34, removed_mos=164, removed_mims=9,
        removed_instance_prefixes=list(REMOVED), rewired_instance_prefixes=list(REWIRED),
        nonmodified_native_terminal_maps_preserved=True, all_component_definitions_preserved=True,
        all_programming_gate_maps_preserved=True, input_to_output_polarity='noninverting',
        node_polarities=dict(selected='noninverting', fine_node='inverting'),
        shared_wire_rc_qualified=False, qualified_phy=False)
    return result, observations, revision


def fixture(out, identity, spec):
    text = source.fixture(out, identity, spec)
    if text.count(source.TOP) != 1:
        raise ValueError('Original native fixture top changed')
    text = text.replace(source.TOP, TOP, 1).replace('OpenLVDS '+source.VERSION+'\n', 'OpenLVDS '+VERSION+'\n', 1)
    match = re.search(r'(?m)^\.print tran (.+)$', text)
    if match is None:
        raise ValueError('Missing original native observation statement')
    nodes = set(re.findall(r'V\(([^)]+)\)', match[1]))
    nodes.discard('XD:restored_b')
    nodes.update('XD:tree0_'+str(k) for k in range(4))
    return text[:match.start()]+'.print tran '+' '.join('V('+n+')' for n in sorted(nodes))+text[match.end():]


def depth_evidence(folder):
    report = json.loads((folder/'summary.json').read_text())
    gates = report['recorded_gates']
    if (folder.parent != ROOT/'build/reports/preconditioned_bank_stage_replay'
            or report.get('analysis_completed') is not True
            or report.get('all_original_native_metrics_reproduced') is not True
            or report.get('native_mos') != 1511 or report.get('programming_gates') != 173
            or report.get('zero_code_fast_quarter_headroom_ps', 0) >= 0
            or gates.get('zero_code_quarter_passed') is not False
            or any(gates.get(k) is not True for k in ('input_timing_stimulus_passed',
                'full_swing_pulses_passed', 'unwrapped_native_epoch_passed', 'pulse_order_and_widths_passed',
                'current_downstream_250ps_slew_domain_passed', 'period_screen_passed',
                'repeated_delay_screen_passed', 'terminal_screen_passed', 'control_settling_passed'))
            or any(sha(ROOT/n) != h for n, h in report['inputs'].items())):
        raise ValueError('Require exact complete reordered-bank isolated quarter-period failure')
    if (report['spec']['coarse'], report['spec']['fine']) != (0, 0):
        raise ValueError('Depth diagnosis must be the actual zero-code trace')
    case = ROOT/report['case']
    original = json.loads((case/'summary.json').read_text())
    if (original['error'] is not None or original['spec'] != report['spec']
            or original['result']['zero_code_fast_quarter_headroom_ps'] != report['zero_code_fast_quarter_headroom_ps']
            or {k: v for k, v in original['result'].items() if k.endswith('_passed')} != gates):
        raise ValueError('Reordered native failure no longer matches its stage diagnosis')
    return [folder/'summary.json', *[ROOT/n for n in report['inputs']]]


def guard_inputs(inputs):
    return {n: h for n, h in inputs.items()
            if not (Path(n).suffix == '.raw' and Path(n).parts[:2] == ('build', 'diagnostics'))}


def prepare(parent, evidence):
    manifest = source.bound(parent)
    previous = manifest['identity']
    report = json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', cases=4, errors=0, qualified_phy=False)
            or report['comparison'] != source.compare(report['rows'])
            or report['comparison']['component_hypothesis_passed'] is not False):
        raise ValueError('Require complete failed original native bank reference')
    paths = depth_evidence(evidence)+[parent/n for n in ('manifest.json', 'summary.json', 'state.json', 'bank.spice')]
    for task, row in zip(manifest['tasks'], report['rows']):
        folder = parent/task['id']
        if (row != json.loads((folder/'summary.json').read_text()) or row['task'] != task
                or row['error'] is not None or any(sha(folder/n) != h for n, h in row['files'].items())):
            raise ValueError('Complete original native bank evidence changed')
        paths += [folder/'summary.json', *[folder/n for n in row['files']]]
    bank, observations, revision = transform((parent/'bank.spice').read_text(), previous['observations'])
    paths += [ROOT/n for n in previous['inputs']]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}
    identity = dict(previous, version=VERSION, parent=str(parent.relative_to(ROOT)),
        depth_evidence=str(evidence.relative_to(ROOT)), specs=specifications(), inputs=inputs,
        guards=guard_inputs(inputs), observations=observations, native_revision=revision,
        max_workers=1, priority=1, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'bank.spice').write_text(bank)
    tasks = []
    for k, spec in enumerate(identity['specs']):
        folder = out/str(k)
        folder.mkdir()
        (folder/'bench.cir').write_text(fixture(out, identity, spec))
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
        bank_sha256=sha(out/'bank.spice'), qualified_phy=False))
    return out


def bound(out, full=True):
    manifest = json.loads((out/'manifest.json').read_text())
    i = manifest['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['guards'] != guard_inputs(i['inputs'])
            or (i['max_workers'], i['priority']) != (1, 1) or engine() != 'ngspice' or provenance() != i['simulator']
            or any(sha(ROOT/n) != h for n, h in (i['inputs'] if full else i['guards']).items())
            or any(sha(Path(n)) != h for n, h in {**i['pdk_files'], **i['external_files']}.items())
            or sha(out/'bank.spice') != manifest['bank_sha256'] or len(manifest['tasks']) != 4):
        raise ValueError('Two-stage fine-bank native context changed')
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in i['ports']}
    if source.native.mapped_mos((out/'bank.spice').read_text(), TOP, pins, 'XD') != i['observations']['devices']:
        raise ValueError('Actual two-stage native terminal map changed')
    for k, task in enumerate(manifest['tasks']):
        path = out/str(k)/'bench.cir'
        if (task != dict(id=str(k), spec=i['specs'][k], deck_sha256=sha(path))
                or path.read_text() != fixture(out, i, task['spec'])):
            raise ValueError('Original four-point two-stage bank fixture changed')
    return manifest


def measure(folder, identity, spec):
    return dict(source.measure(folder, identity, spec), whole_bank_rc_retained=False,
        electrical_qualification_passed=False, qualified_phy=False, scope=SCOPE)


def compare(rows):
    if len(rows) != 4 or any(r['error'] is not None or r['result'] is None for r in rows):
        return None
    if [r['spec'] for r in rows] != specifications():
        raise ValueError('Require complete original two-stage zero/duty/coarse coverage')
    complete = all(len(r['result']['edge_delays_ps'][e]) == 8
                   and all(np.isfinite(v) and v > 0 for v in r['result']['edge_delays_ps'][e])
                   for r in rows for e in ('rise', 'fall'))
    overlap = {e: min(v for r in rows[1:3] for v in r['result']['edge_delays_ps'][e])
               - max(rows[3]['result']['edge_delays_ps'][e]) if complete else None for e in ('rise', 'fall')}
    return dict(component_hypothesis_passed=bool(complete
        and all(r['result']['current_clock_interface_screen_passed'] for r in rows)
        and all(v > 0 for v in overlap.values())), conservative_coarse_overlap_ps=overlap,
        complete_four_point_native_screen=True, shared_wire_rc_qualified=False,
        all_pvt_covered=False, electrical_qualification_passed=False, qualified_phy=False)


def run(out):
    manifest = bound(out)
    identity = manifest['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain existing or partial two-stage native experiment')
        atomic(out/'state.json', dict(status='running', qualified_phy=False))
        rows = []
        for task in manifest['tasks']:
            folder = out/task['id']
            result = error = None
            try:
                with lease(ROOT, priority=1, label=CONTEXT+'_'+task['id']):
                    bound(out, full=False)
                    process = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'),
                        '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                (folder/'console.log').write_text(process.stdout+process.stderr)
                process.check_returncode()
                result = measure(folder, identity, task['spec'])
            except Exception as exception:
                error = str(exception)
            row = dict(task=task, spec=task['spec'], result=result, error=error,
                files={p.name: sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json', row)
            rows.append(row)
        bound(out)
        atomic(out/'summary.json', dict(rows=rows, comparison=compare(rows), scope=SCOPE, qualified_phy=False))
        atomic(out/'state.json', dict(status='complete', cases=4,
            errors=sum(r['error'] is not None for r in rows), qualified_phy=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'campaign'))
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if args.action in ('prepare', 'campaign'):
        if args.evidence is None:
            parser.error('--evidence required')
        artifact = prepare(artifact, args.evidence.resolve())
        print(artifact, flush=True)
    if args.action in ('run', 'campaign'):
        print(run(artifact), flush=True)
