#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replace only the 31 isolated MOSCAP fine cells by qualified native MIM cells."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
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
VERSION = 'qualified-mim-only-substitution-behind-regular-fine-isolation-v321.1'
CONTEXT = 'mim_isolated_fine_bank_v321'
TOP = 'openlvds_mim_isolated_fine_v321'
OLD_UNIT = 'openlvds_measured_gangs_b2_v125_unit'
MODELS = {'2x2': 'openlvds_mim_switch_unit_v2', '2x3': 'openlvds_mim_switch_2x3_v2'}
CAD = source.source.CAD
PORTS = ['NODE', 'EN', 'ENB', 'VDD', 'VSS']
PREFIXES = tuple('XD:Xfine_unit'+str(k)+':' for k in range(31))
SCOPE = ('Only 31 fine cells replaced by retained qualified 2x2/2x3 MIM native RC; '
         'unchanged coarse tree, isolation/output drivers, controls and all eight startup cycles; '
         'new shared wires ideal, no whole-bank RC/dense/update/all-PVT/DLL/PHY admission')


def specifications():
    return [dict(s, fine_cell=variant) for variant in MODELS for s in source.specifications()]


def transform(bank, previous, cell, variant):
    if variant not in MODELS:
        raise ValueError('Unknown retained MIM variant')
    model = MODELS[variant]
    definitions = source.native.definitions(bank)
    added = source.native.definitions(cell)
    if (set(added) != {model} or added[model][0] != PORTS
            or (model in definitions and source.cell_definition(bank, model) != cell)
            or definitions[OLD_UNIT][0] != PORTS):
        raise ValueError('MIM namespace or fine-cell supply/public port order changed')
    _, unit = source.inventory.native_leaves(collapse(cell), model)
    if (sum('fet_' in d['model'] for d in unit) != 3
            or sum('cap_mim' in d['model'] for d in unit) != 2 or len(unit) != 5):
        raise ValueError('Require the exact native three-MOS/two-MIM fine cell')
    body = definitions[source.TOP][1]
    before = source.cell_definition(bank, source.TOP)
    after = before
    for k in range(31):
        call = [f'Xfine_unit{k}', 'fine_node', f'fine{k}', f'fine_b{k}', 'VPWR', 'VGND', OLD_UNIT]
        if [w for w in body if w[0] == call[0]] != [call]:
            raise ValueError('Original isolated fine-cell wiring changed')
        after = after.replace(' '.join(call)+'\n', ' '.join(call[:-1]+[model])+'\n', 1)
    after = after.replace('.subckt '+source.TOP+' ', '.subckt '+TOP+' ', 1)
    after = after.replace('.ends '+source.TOP+'\n', '.ends '+TOP+'\n', 1)
    result = bank.replace(before, after, 1)+('' if model in definitions else '\n'+cell)
    for name in definitions:
        if name != source.TOP and source.cell_definition(result, name) != source.cell_definition(bank, name):
            raise ValueError('Unrelated native macro definition changed')
    ports = definitions[source.TOP][0]
    pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = source.native.mapped_mos(result, TOP, pins, 'XD')
    old = {d['name']: d for d in previous['devices']}
    new = {d['name']: d for d in devices}
    if (len(old) != 1529 or len(devices) != 1467 or len(new) != 1467
            or sum(n.startswith(PREFIXES) for n in old) != 155
            or sum(n.startswith(PREFIXES) for n in new) != 93
            or any(new.get(n) != d for n, d in old.items() if not n.startswith(PREFIXES))):
        raise ValueError('Non-fine native terminals or exact fine-cell MOS census changed')
    expected_old = {prefix+leaf for prefix in PREFIXES for leaf in ('X0', 'X4', 'X5')}
    old_gates = [g for g in previous['programming_gates'] if g['device'].startswith(PREFIXES)]
    if {g['device'] for g in old_gates} != expected_old or len(old_gates) != 93:
        raise ValueError('Original typed fine programming-gate coverage changed')
    gates = [g for g in previous['programming_gates'] if not g['device'].startswith(PREFIXES)]
    if len(gates) != 80 or any(new[g['device']]['terminals'][1] != g['gate_node'] for g in gates):
        raise ValueError('Non-fine programming-gate map changed')
    for k, prefix in enumerate(PREFIXES):
        for leaf, control in (('X0', f'fine_b{k}'), ('X3', f'fine{k}'), ('X4', f'fine_b{k}')):
            name = prefix+leaf
            d = new[name]
            expected_gate = prefix+('EN.t0' if leaf == 'X3' else 'ENB.t2' if leaf == 'X0' else 'ENB.t1')
            if d['terminals'][1] != expected_gate:
                raise ValueError('Actual distributed MIM switch programming-gate node changed')
            gates.append(dict(device=name, gate_node=d['terminals'][1], control=control, kind='fine'))
    if len(gates) != 173 or len({g['device'] for g in gates}) != 173 or len(previous['controls']) != 86:
        raise ValueError('Incomplete typed programming or logical control observations')
    _, leaves = source.inventory.native_leaves(collapse(result), TOP)
    if (sum('fet_' in d['model'] for d in leaves) != 1467
            or sum('cap_mim' in d['model'] for d in leaves) != 74 or len(leaves) != 1541):
        raise ValueError('Full native 1467-MOS/74-MIM bank inventory changed')
    observations = dict(devices=devices, controls=previous['controls'], programming_gates=gates)
    revision = dict(native_mos=1467, native_mims=74, changed_instance_prefixes=list(PREFIXES),
        removed_fine_mos=155, added_fine_mos=93, unchanged_nonfine_native_terminal_maps=True,
        all_unrelated_native_definitions_preserved=True, all_173_actual_programming_gates_observed=True,
        logical_controls_preserved=True, shared_wire_rc_qualified=False, qualified_phy=False)
    return result, observations, revision


def materials(parent):
    command = ('import sys;from pathlib import Path;sys.path.insert(0,"scripts");'
               'import qualify_retained_mim_fine_rc_v320 as q;q.bound(Path(sys.argv[1]))')
    check = subprocess.run([CAD, '-c', command, str(parent)], cwd=ROOT, capture_output=True, text=True)
    if check.returncode:
        raise ValueError('Retained MIM qualification binding failed: '+check.stderr[-2000:])
    manifest = json.loads((parent/'manifest.json').read_text())
    identity = manifest['identity']
    report = json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or report.get('retained_component_rc_qualified') is not True
            or [r['variant'] for r in report['rows']] != list(MODELS)
            or any(sha(parent/n) != h for n, h in report['files'].items())):
        raise ValueError('Require both complete unchanged current MIM component RC proofs')
    libraries = {}
    for row in report['rows']:
        variant = row['variant']
        proof = row['rc_proof']
        if (row['macro'] != MODELS[variant] or row['retained_component_rc_qualified'] is not True
                or any(proof.get(k) is not True for k in
                       ('component_rc_passed', 'exact_reduction_regenerated', 'native_topology_verified'))
                or proof['independent_terminal_current_witness']['proof']['passed'] is not True):
            raise ValueError('Retained MIM native/exact-reduction/Schur gate failed')
        info = row['extraction']
        if sha(ROOT/info['netlist']) != info['netlist_sha256']:
            raise ValueError('Qualified MIM numerical model changed')
        libraries[variant] = source.cell_definition((ROOT/info['netlist']).read_text(), MODELS[variant])
    paths = [parent/n for n in ('manifest.json', 'summary.json', 'state.json', *report['files'])]
    paths += [ROOT/n for n in identity['inputs']]
    return libraries, paths, identity


def fixture(out, identity, spec):
    variant = spec['fine_cell']
    text = source.fixture(out/variant, dict(identity, observations=identity['observations'][variant]), spec)
    if text.count(source.TOP) != 1:
        raise ValueError('Original native bank fixture top changed')
    return text.replace(source.TOP, TOP, 1).replace('OpenLVDS '+source.VERSION+'\n', 'OpenLVDS '+VERSION+'\n', 1)


def guard_inputs(inputs):
    return {n: h for n, h in inputs.items()
            if not (Path(n).suffix == '.raw' and Path(n).parts[:2] == ('build', 'diagnostics'))}


def prepare(parent, components):
    manifest = source.bound(parent)
    previous = manifest['identity']
    report = json.loads((parent/'summary.json').read_text())
    if json.loads((parent/'state.json').read_text()) != dict(status='complete', cases=4, errors=0, qualified_phy=False):
        raise ValueError('Require the naturally completed original four-point native bank')
    if (report['comparison'] != source.compare(report['rows'])
            or report['comparison']['component_hypothesis_passed'] is not False
            or any(v >= 0 for v in report['comparison']['conservative_coarse_overlap_ps'].values())):
        raise ValueError('Require the exact original both-edge fine/coarse range failure')
    paths = [parent/n for n in ('manifest.json', 'summary.json', 'state.json', 'bank.spice')]
    for task, row in zip(manifest['tasks'], report['rows']):
        folder = parent/task['id']
        if (row != json.loads((folder/'summary.json').read_text()) or row['task'] != task
                or row['error'] is not None or any(sha(folder/n) != h for n, h in row['files'].items())
                or source.measure(folder, previous, row['spec']) != row['result']):
            raise ValueError('Original complete native reference metrics or bytes changed')
        paths += [folder/'summary.json', *[folder/n for n in row['files']]]
    cells, files, rc = materials(components)
    paths += files+[ROOT/n for n in previous['inputs']]
    bank = (parent/'bank.spice').read_text()
    libraries = {v: transform(bank, previous['observations'], cells[v], v) for v in MODELS}
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}
    identity = dict(previous, version=VERSION, parent=str(parent.relative_to(ROOT)),
        components=str(components.relative_to(ROOT)), specs=specifications(), inputs=inputs, guards=guard_inputs(inputs),
        external_files={**previous['external_files'], **rc['external_files']},
        observations={v: libraries[v][1] for v in MODELS}, native_revision={v: libraries[v][2] for v in MODELS},
        max_workers=1, priority=1, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for variant in MODELS:
        folder = out/variant
        folder.mkdir()
        (folder/'bank.spice').write_text(libraries[variant][0])
        hashes[variant+'/bank.spice'] = sha(folder/'bank.spice')
    tasks = []
    for k, spec in enumerate(identity['specs']):
        folder = out/str(k)
        folder.mkdir()
        (folder/'bench.cir').write_text(fixture(out, identity, spec))
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json', dict(identity=identity, tasks=tasks, libraries=hashes, qualified_phy=False))
    return out


def bound(out, full=True):
    manifest = json.loads((out/'manifest.json').read_text())
    i = manifest['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['guards'] != guard_inputs(i['inputs'])
            or i['max_workers'] != 1 or i['priority'] != 1 or engine() != 'ngspice' or provenance() != i['simulator']
            or any(sha(ROOT/n) != h for n, h in (i['inputs'] if full else i['guards']).items())
            or any(sha(Path(n)) != h for n, h in {**i['pdk_files'], **i['external_files']}.items())
            or set(manifest['libraries']) != {v+'/bank.spice' for v in MODELS}
            or any(sha(out/n) != h for n, h in manifest['libraries'].items()) or len(manifest['tasks']) != 8):
        raise ValueError('MIM isolated fine-bank native context changed')
    for variant in MODELS:
        bank = (out/variant/'bank.spice').read_text()
        pins = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in i['ports']}
        if source.native.mapped_mos(bank, TOP, pins, 'XD') != i['observations'][variant]['devices']:
            raise ValueError('Actual native MIM-bank terminal observations changed')
    for k, task in enumerate(manifest['tasks']):
        path = out/str(k)/'bench.cir'
        if (task != dict(id=str(k), spec=i['specs'][k], deck_sha256=sha(path))
                or path.read_text() != fixture(out, i, task['spec'])):
            raise ValueError('Original eight-case MIM-bank native fixture changed')
    return manifest


def measure(folder, identity, spec):
    local = dict(identity, observations=identity['observations'][spec['fine_cell']])
    return dict(source.measure(folder, local, spec), whole_bank_rc_retained=False,
                electrical_qualification_passed=False, qualified_phy=False, scope=SCOPE)


def compare(rows):
    if len(rows) != 8 or any(r['error'] is not None or r['result'] is None for r in rows):
        return None
    if [r['spec'] for r in rows] != specifications():
        raise ValueError('Require all original MIM variants/zero/duty/coarse cases')
    result = []
    for variant in MODELS:
        group = [r for r in rows if r['spec']['fine_cell'] == variant]
        complete = all(len(r['result']['edge_delays_ps'][e]) == 8
                       and all(np.isfinite(v) and v > 0 for v in r['result']['edge_delays_ps'][e])
                       for r in group for e in ('rise', 'fall'))
        overlap = {e: min(v for r in group[1:3] for v in r['result']['edge_delays_ps'][e])
                   - max(group[3]['result']['edge_delays_ps'][e]) if complete else None
                   for e in ('rise', 'fall')}
        result.append(dict(variant=variant, conservative_coarse_overlap_ps=overlap,
            component_hypothesis_passed=bool(complete
                and all(r['result']['current_clock_interface_screen_passed'] for r in group)
                and all(v > 0 for v in overlap.values()))))
    return dict(variants=result, complete_eight_case_native_screen=True,
        any_component_hypothesis_passed=any(r['component_hypothesis_passed'] for r in result),
        shared_wire_rc_qualified=False, all_pvt_covered=False, electrical_qualification_passed=False, qualified_phy=False)


def run(out):
    manifest = bound(out)
    identity = manifest['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain existing or partial MIM-bank experiment')
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
            atomic(folder/'summary.json', dict(task=task, spec=task['spec'], result=result, error=error,
                files={p.name: sha(p) for p in folder.iterdir() if p.is_file()}))
            rows.append(json.loads((folder/'summary.json').read_text()))
        bound(out)
        atomic(out/'summary.json', dict(rows=rows, comparison=compare(rows), scope=SCOPE, qualified_phy=False))
        atomic(out/'state.json', dict(status='complete', cases=8,
            errors=sum(r['error'] is not None for r in rows), qualified_phy=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'campaign'))
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--components', type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if args.action in ('prepare', 'campaign'):
        if args.components is None:
            parser.error('--components is required')
        artifact = prepare(artifact, args.components.resolve())
        print(artifact, flush=True)
    if args.action in ('run', 'campaign'):
        print(run(artifact), flush=True)
