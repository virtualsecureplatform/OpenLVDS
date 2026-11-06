#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Move a qualified small inverter ahead of the loaded fine-delay stage."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import probe_tapered_regenerated_bank_v310 as base
import analyze_regular_regenerated_stages_v300 as diagnosis

ROOT = base.ROOT
sha = base.sha
source = base.source
TOP = 'openlvds_preconditioned_fine_v315'
VERSION = 'qualified-p10n8-preconditioner-before-loaded-fine-stage-v315.1'
CONTEXT = 'preconditioned_fine_bank_v315'
SMALL = base.MODELS['p10n8']
LARGE = source.MODEL
NATIVE_MOS = 1511
SCOPE = ('Reordered qualified P10/N8 -> loaded P20/N16 -> final P20/N16, '
         'same fine cells/coarse tree/controls and three inversions; new shared wires ideal, '
         'no routed-bank, dense/update, all-clock/PVT, DLL or PHY admission')


def specifications():
    return [dict(s, regenerator='p10n8_before_loaded_p20n16_then_p20n16')
            for s in source.specifications()]


def transform(bank, previous):
    definitions = source.native.definitions(bank)
    expected = {
        'Xfine_isolate': ['Xfine_isolate', 'selected', 'fine_node', 'VGND', 'VPWR', LARGE],
        'Xfine_regenerate0': ['Xfine_regenerate0', 'fine_node', 'restored_b', 'VGND', 'VPWR', SMALL],
        'Xfine_regenerate1': ['Xfine_regenerate1', 'restored_b', 'OUT', 'VGND', 'VPWR', LARGE],
    }
    for model in (SMALL, LARGE):
        if definitions[model][0] != ['A', 'Y', 'VGND', 'VPWR']:
            raise ValueError('Qualified inverter public port order changed')
    body = definitions[base.TOP][1]
    for name, row in expected.items():
        if [w for w in body if w[0] == name] != [row]:
            raise ValueError('Prepared post-fine taper stage topology changed')
    if any('conditioned' in w[1:] for w in body):
        raise ValueError('Preconditioner private signal namespace collision')
    replacement = {
        'Xfine_regenerate0': ['Xfine_regenerate0', 'selected', 'conditioned', 'VGND', 'VPWR', SMALL],
        'Xfine_isolate': ['Xfine_isolate', 'conditioned', 'fine_node', 'VGND', 'VPWR', LARGE],
        'Xfine_regenerate1': ['Xfine_regenerate1', 'fine_node', 'OUT', 'VGND', 'VPWR', LARGE],
    }
    before = source.cell_definition(bank, base.TOP)
    after = before
    for name, row in expected.items():
        after = after.replace(' '.join(row)+'\n', ' '.join(replacement[name])+'\n', 1)
    after = after.replace('.subckt '+base.TOP+' ', '.subckt '+TOP+' ', 1)
    after = after.replace('.ends '+base.TOP+'\n', '.ends '+TOP+'\n', 1)
    result = bank.replace(before, after, 1)
    for model in definitions:
        if model != base.TOP and source.cell_definition(result, model) != source.cell_definition(bank, model):
            raise ValueError('Unrelated qualified component definition changed')
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in definitions[base.TOP][0]}
    devices = source.native.mapped_mos(result, TOP, pins, 'XD')
    old = {d['name']: d for d in previous['devices']}
    new = {d['name']: d for d in devices}
    allowed = tuple('XD:'+name+':' for name in expected)
    if (len(old) != NATIVE_MOS or len(new) != NATIVE_MOS or len(devices) != NATIVE_MOS
            or old.keys() != new.keys()
            or any(new[n] != d for n, d in old.items() if not n.startswith(allowed))):
        raise ValueError('Unrelated native terminal map or exact MOS inventory changed')
    gates = [dict(g, gate_node=new[g['device']]['terminals'][1]) for g in previous['programming_gates']]
    if gates != previous['programming_gates'] or len(gates) != 173 or len(previous['controls']) != 86:
        raise ValueError('Typed programming gates or logical controls changed')
    _, leaves = source.inventory.native_leaves(base.collapse(result), TOP)
    counts = {k: sum(('fet_' in d['model']) == k for d in leaves) for k in (True, False)}
    if counts != {True: NATIVE_MOS, False: 43}:
        raise ValueError('Native MOS/MIM census changed')
    observations = dict(devices=devices, controls=previous['controls'], programming_gates=gates)
    proof = dict(native_mos=NATIVE_MOS, native_mims=43,
        reordered_stage_calls=list(replacement.values()), changed_instance_prefixes=list(allowed),
        all_unrelated_native_terminal_maps_preserved=True,
        all_qualified_component_definitions_preserved=True, all_programming_gates_preserved=True,
        input_to_output_polarity='noninverting',
        node_polarities=dict(selected='inverting', conditioned='noninverting', fine_node='inverting'),
        shared_wire_rc_qualified=False, qualified_phy=False)
    return result, observations, proof


def fixture(out, identity, spec):
    text = source.fixture(out, identity, spec)
    if text.count(source.TOP) != 1:
        raise ValueError('Original native fixture top changed')
    text = text.replace(source.TOP, TOP, 1)
    text = text.replace('OpenLVDS '+source.VERSION+'\n', 'OpenLVDS '+VERSION+'\n', 1)
    match = re.search(r'(?m)^\.print tran (.+)$', text)
    if match is None:
        raise ValueError('Missing original native observation statement')
    probes = set(re.findall(r'V\(([^)]+)\)', match[1]))
    probes.discard('XD:restored_b')
    probes.add('XD:conditioned')
    statement = '.print tran '+' '.join('V('+name+')' for name in sorted(probes))
    return text[:match.start()] + statement + text[match.end():]


def require_stage_reference(evidence, original, baseline):
    manifest = json.loads((evidence/'manifest.json').read_text())
    identity = manifest['identity']
    report = json.loads((evidence/'summary.json').read_text())
    if (evidence.parent != ROOT/'build/diagnostics'/diagnosis.CONTEXT
            or identity['version'] != diagnosis.VERSION
            or evidence.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in identity['inputs'].items())
            or report.get('analysis_completed') is not True or len(report['rows']) != 1):
        raise ValueError('Require unchanged complete original zero-code stage diagnosis')
    row = report['rows'][0]
    if (row['case'] != str((original/'0').relative_to(ROOT))
            or row['task'] != baseline['task'] or row['native_mos'] != 1529
            or row['programming_gates'] != 173 or row['all_original_native_metrics_reproduced'] is not True):
        raise ValueError('Stage diagnosis does not bind the completed baseline zero case')
    for edge in ('rise', 'fall'):
        part = row['decomposition'][edge]
        if (part['total_delays_ps'] != baseline['result']['edge_delays_ps'][edge]
                or part['maximum_sum_residual_ps'] > 1e-6):
            raise ValueError('All eight original stage delays must reproduce')
    return identity


def prepare(parent, evidence):
    manifest = base.bound(parent)
    previous = manifest['identity']
    original = ROOT/previous['parent']
    baseline, baseline_paths = base.require_baseline(original, json.loads((original/'manifest.json').read_text()))
    di = require_stage_reference(evidence, original, baseline)
    bank, observations, proof = transform((parent/'p10n8/bank.spice').read_text(), previous['observations']['p10n8'])
    paths = [parent/'manifest.json', parent/'p10n8/bank.spice', *baseline_paths,
             *[evidence/n for n in ('manifest.json', 'summary.json', 'state.json')]]
    paths += [ROOT/n for n in {*previous['inputs'], *di['inputs']}]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(previous, version=VERSION, parent=str(parent.relative_to(ROOT)),
        original=str(original.relative_to(ROOT)), stage_reference=str(evidence.relative_to(ROOT)),
        observations=observations, native_revision=proof, specs=specifications(),
        inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))},
        max_workers=1, priority=1, scope=SCOPE)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT/'build/diagnostics'/CONTEXT/digest
    out.mkdir(parents=True, exist_ok=False)
    (out/'bank.spice').write_text(bank)
    tasks = []
    for k, spec in enumerate(identity['specs']):
        folder = out/str(k)
        folder.mkdir()
        (folder/'bench.cir').write_text(fixture(out, identity, spec))
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(folder/'bench.cir')))
    base.atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
                                        bank_sha256=sha(out/'bank.spice'), qualified_phy=False))
    return out


def bound(out):
    manifest = json.loads((out/'manifest.json').read_text())
    identity = manifest['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or identity['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or identity['specs'] != specifications() or identity['max_workers'] != 1 or identity['priority'] != 1
            or base.engine() != 'ngspice' or base.provenance() != identity['simulator']
            or any(sha(ROOT/n) != h for n, h in identity['inputs'].items())
            or any(sha(Path(n)) != h for n, h in {**identity['pdk_files'], **identity['external_files']}.items())
            or sha(out/'bank.spice') != manifest['bank_sha256'] or len(manifest['tasks']) != 4
            or len(identity['observations']['devices']) != NATIVE_MOS):
        raise ValueError('Preconditioned native bank experiment changed')
    for k, task in enumerate(manifest['tasks']):
        path = out/str(k)/'bench.cir'
        if (task != dict(id=str(k), spec=identity['specs'][k], deck_sha256=sha(path))
                or path.read_text() != fixture(out, identity, task['spec'])):
            raise ValueError('Original four-point full native fixture changed')
    return manifest


def measure(folder, identity, spec):
    return dict(source.measure(folder, identity, spec), whole_bank_rc_retained=False,
                new_common_routing_qualified=False, electrical_qualification_passed=False,
                qualified_phy=False, scope=SCOPE)


def compare(rows):
    if len(rows) != 4 or any(r['error'] is not None or r['result'] is None for r in rows):
        return None
    if [r['spec'] for r in rows] != specifications():
        raise ValueError('Require complete original zero, both-duty fine and first-coarse coverage')
    complete = all(len(r['result']['edge_delays_ps'][e]) == 8
                   and all(np.isfinite(v) and v > 0 for v in r['result']['edge_delays_ps'][e])
                   for r in rows for e in ('rise', 'fall'))
    overlap = {e: min(v for r in rows[1:3] for v in r['result']['edge_delays_ps'][e])
               - max(rows[3]['result']['edge_delays_ps'][e]) if complete else None
               for e in ('rise', 'fall')}
    return dict(component_hypothesis_passed=bool(complete
        and all(r['result']['current_clock_interface_screen_passed'] for r in rows)
        and all(v > 0 for v in overlap.values())),
        conservative_coarse_overlap_ps=overlap, complete_four_point_native_screen=True,
        shared_wire_rc_qualified=False, all_pvt_covered=False,
        electrical_qualification_passed=False, qualified_phy=False)


def run(out):
    manifest = bound(out)
    identity = manifest['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain previous or partial preconditioned-bank experiment')
        base.atomic(out/'state.json', dict(status='running', qualified_phy=False))
        rows = []
        for task in manifest['tasks']:
            folder = out/task['id']
            result = error = None
            try:
                with base.lease(ROOT, priority=1, label=CONTEXT+'_'+task['id']):
                    bound(out)
                    process = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'),
                        '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                (folder/'console.log').write_text(process.stdout+process.stderr)
                process.check_returncode()
                result = measure(folder, identity, task['spec'])
            except Exception as exception:
                error = str(exception)
            row = dict(task=task, spec=task['spec'], result=result, error=error,
                       files={p.name: sha(p) for p in folder.iterdir() if p.is_file()})
            base.atomic(folder/'summary.json', row)
            rows.append(row)
        bound(out)
        base.atomic(out/'summary.json', dict(rows=rows, comparison=compare(rows), scope=SCOPE, qualified_phy=False))
        base.atomic(out/'state.json', dict(status='complete', cases=4,
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
