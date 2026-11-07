#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check the passed twelve-point counter's physical 5x5 shunt integration."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import preflight_request_taper_counter_v326 as legacy
import plan_request_taper_counter_v327 as planning
import probe_large_shunt_counter_boundaries_v334 as boundary
from audit_rc_comments_v2 import collapse
from lvs_utils import strict_setup, clean_match
from probe_digital_dcc_v2 import atomic

ROOT = legacy.ROOT
VERSION = 'passed-5x5-shunt-23-macro-native-counter-integration-preflight-v343.1'
CONTEXT = 'shunted_counter_material_preflight_v343'
NAME = 'openlvds_shunted_counter_v343'
PORTS = legacy.base.physical.PORTS
CAP = 'openlvds_counter_output_mim5_v336'
ROLE = 'low0_output_extra_v331'
BOUNDARY = ROOT/'build/diagnostics/large_shunt_counter_boundaries_v334/89ff7c952da2161a'
PLAN = ROOT/'build/diagnostics/request_taper_counter_plan_v327/d8e29c7f91c15d0d'
CAPRC = ROOT/'build/diagnostics/counter_output_mim5_rc_v337/75108e50b46db51f'
REPLAYS = ['request_taper_large_shunt_native_replay/20261107T061754Z'] + [
    'large_shunt_counter_boundary_replay/'+stamp for stamp in (
        '20261107T065234Z', '20261107T065804Z', '20261107T073309Z',
        '20261107T074340Z', '20261107T075736Z', '20261107T080542Z',
        '20261107T082231Z', '20261107T082815Z', '20261107T083607Z',
        '20261107T084219Z', '20261107T091013Z')]
sha = boundary.sha
SCOPE = ('Complete twelve-point native boundary evidence and actual 23-macro '
         '5x5-shunted counter material/topology/parameter compatibility only; '
         'no new counter placement/wiring/GDS/shared-RC/transient/PVT/DLL/PHY admission')


def add_shunt(cells):
    if (len(cells) != 22 or len({c['name'] for c in cells}) != 22
            or any(c['name'] == ROLE for c in cells)
            or next((c['pins'].get('Y') for c in cells if c['name'] == 'low0_set_pair'), None) != 'low0_sn'):
        raise ValueError('Require unchanged 22-role counter and original low0 setter output')
    return deepcopy(cells)+[dict(name=ROLE, model=CAP, pins=dict(Y='low0_sn', VGND='VGND'))]


def reference(cells, macros):
    definitions = legacy.native.definitions
    blocks = []
    orders = {}
    for model, material in sorted(macros.items()):
        file = ROOT/material['folder']/(model+'.lvs.spice')
        text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', file.read_text())
        order, body = definitions(text)[model+'_flat']
        legacy.inventory.native_leaves(text, model+'_flat')
        orders[model] = order
        blocks += ['.subckt '+model+' '+' '.join(order), *[' '.join(w) for w in body], '.ends '+model]
    blocks += ['.subckt '+NAME+' '+' '.join(PORTS)]
    for cell in cells:
        order = orders[cell['model']]
        if set(order) != set(cell['pins']):
            raise ValueError('Native counter macro/public electrode interface changed')
        blocks.append('X'+cell['name']+' '+' '.join(cell['pins'][p] for p in order)+' '+cell['model'])
    return '\n'.join(blocks+['.ends '+NAME, ''])


def require_boundaries(manifest, state, report):
    rows = report.get('rows', [])
    if (state != dict(status='complete', cases=12, errors=0, qualified_phy=False)
            or len(rows) != 12 or [r['task'] for r in rows] != manifest['tasks']
            or report.get('comparison') != boundary.assess(rows)
            or report['comparison'].get('component_hypothesis_passed') is not True
            or any(r.get('error') is not None or not boundary.point_passed(r.get('result')) for r in rows)):
        raise ValueError('Require all twelve complete passing original native counter boundaries')


def merge_expected(target, values):
    for name, digest in values.items():
        if name in target and target[name] != digest:
            raise ValueError('Conflicting captured native input hashes: '+name)
        target[name] = digest


def boundaries():
    manifest = boundary.bound(BOUNDARY, full=False)
    report = json.loads((BOUNDARY/'summary.json').read_text())
    require_boundaries(manifest, json.loads((BOUNDARY/'state.json').read_text()), report)
    paths = [BOUNDARY/n for n in ('manifest.json', 'summary.json', 'state.json')]
    expected = dict(manifest['identity']['inputs'])
    merge_expected(expected, {str((BOUNDARY/n).relative_to(ROOT)): h for n, h in manifest['libraries'].items()})
    for k, (row, replay) in enumerate(zip(report['rows'], REPLAYS)):
        folder = BOUNDARY/str(k)
        if row != json.loads((folder/'summary.json').read_text()):
            raise ValueError('Completed native boundary result changed')
        proof_file = ROOT/'build/reports'/replay/'summary.json'
        proof = json.loads(proof_file.read_text())
        if len(proof.get('rows', [])) != 1:
            raise ValueError('Require one exact native point per independent replay')
        witness = proof['rows'][0]
        actual = folder
        if k == 0:
            retained = json.loads((folder/'retained_case.json').read_text())
            actual = ROOT/retained['source_case']
            old = json.loads((actual/'summary.json').read_text())
            if (sha(actual/'summary.json') != retained['original_summary_sha256']
                    or old['files'] != retained['original_files']
                    or dict(old['result'], scope=boundary.SCOPE) != row['result']):
                raise ValueError('Retained original native point changed')
        if (proof.get('all_original_native_metrics_reproduced') is not True
                or proof.get('parameters_changed') is not False
                or witness.get('all_original_native_metrics_reproduced') is not True
                or witness.get('native_mos') != 808 or witness.get('case') != str(actual.relative_to(ROOT))
                or witness.get('recorded_gates') != {n: v for n, v in row['result'].items() if n.endswith('_passed')}):
            raise ValueError('Independent complete native boundary replay changed')
        paths += [proof_file, folder/'summary.json', *[folder/n for n in row['files']]]
        merge_expected(expected, proof['inputs'])
        merge_expected(expected, {str((folder/n).relative_to(ROOT)): h for n, h in row['files'].items()})
    return manifest, report, paths, expected


def cap_material():
    code = '''import sys,json
from pathlib import Path
sys.path.insert(0,"scripts")
import qualify_counter_output_mim5_rc_v337 as q
folder=Path(sys.argv[1]);i=q.bound(folder);r=json.loads((folder/"summary.json").read_text())
if (json.loads((folder/"state.json").read_text())!=dict(status="complete",passed=True,qualified_phy=False)
    or r.get("capacitor_local_rc_qualified") is not True
    or any(q.sha(folder/n)!=h for n,h in r["files"].items())
    or any(q.sha(q.ROOT/n)!=h for n,h in r["extracted_files"].items())):raise ValueError("Native 5x5 MIM RC changed")
physical=q.ROOT/i["parent"];p=json.loads((physical/"summary.json").read_text())
row=dict(p["physical"],ports=p["plan"]["ports"],macro=q.NAME,
    gds_sha256=q.sha(physical/(q.NAME+".gds")),lef_sha256=q.sha(physical/(q.NAME+".lef")))
files=[folder/n for n in ("manifest.json","summary.json","state.json",*r["files"])]+[physical/n for n in ("manifest.json","summary.json","state.json",*p["files"])]
expected=dict(i["inputs"]);expected.update(r["extracted_files"])
print(json.dumps(dict(folder=str(physical.relative_to(q.ROOT)),row=row,files=[str(f.relative_to(q.ROOT)) for f in files],expected=expected)))
'''
    process = subprocess.run([legacy.assembly.repaired.CAD, '-c', code, str(CAPRC)],
                             cwd=ROOT, capture_output=True, text=True, check=True)
    result = json.loads(process.stdout)
    if result['row']['macro'] != CAP:
        raise ValueError('Unexpected qualified 5x5 output shunt')
    return result


def old_materials():
    manifest = json.loads((PLAN/'manifest.json').read_text())
    identity = manifest['identity']
    if (identity['version'] != planning.VERSION
            or PLAN.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or json.loads((PLAN/'state.json').read_text()) != dict(status='complete', planning_completed=True, qualified_phy=False)):
        raise ValueError('Require unchanged complete original 22-role physical materials')
    macros = {name: legacy.assembly.macro(name, ROOT/m['folder'], m['row']) for name, m in identity['macros'].items()}
    return identity, macros


def run():
    manifest, report, paths, expected = boundaries()
    old, macros = old_materials()
    merge_expected(expected, old['inputs'])
    paths += [PLAN/n for n in ('manifest.json', 'summary.json', 'state.json')]
    cap = cap_material()
    merge_expected(expected, cap['expected'])
    paths += [ROOT/n for n in cap['files']]
    macros[CAP] = legacy.assembly.macro(CAP, ROOT/cap['folder'], cap['row'])
    cells = add_shunt(old['cells'])
    proposed = reference(cells, macros)
    actual = (BOUNDARY/'cells.spice').read_text()+'\n'+(BOUNDARY/'pair.spice').read_text()
    _, leaves = legacy.inventory.native_leaves(proposed, NAME)
    _, baseline = legacy.inventory.native_leaves(collapse(actual), legacy.base.NAME)
    parameters = legacy.inventory.compare_parameters(leaves, baseline)
    counts = (sum('fet_' in d['model'] for d in leaves), sum('cap_mim' in d['model'] for d in leaves))
    _, harness = legacy.inventory.native_leaves(collapse(actual), 'openlvds_static_phase_release_loaded_v2')
    loaded = (sum('fet_' in d['model'] for d in harness), sum('cap_mim' in d['model'] for d in harness))
    if counts != (744, 51) or loaded != (808, 57):
        raise ValueError('Require exact 23-role native counter and unchanged downstream loads')
    paths += [ROOT/n for n in expected]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    setup_file = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    paths.append(setup_file)
    inputs = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha(p) for p in sorted(set(paths))}
    if any(inputs.get(n) != h for n, h in expected.items()):
        raise ValueError('Captured native evidence or physical material bytes changed')
    identity = dict(version=VERSION, cells=cells, macros=macros, inputs=inputs, scope=SCOPE,
        boundaries=str(BOUNDARY.relative_to(ROOT)), original_plan=str(PLAN.relative_to(ROOT)),
        cap_rc=str(CAPRC.relative_to(ROOT)), candidate_sha256=hashlib.sha256(proposed.encode()).hexdigest(),
        native_counter_mos=744, native_counter_mims=51)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    atomic(out/'manifest.json', dict(identity=identity, qualified_phy=False))
    atomic(out/'state.json', dict(status='checking', qualified_phy=False))
    try:
        candidate = out/'proposed_counter.sch.spice'
        original = out/'passed_counter_collapsed.spice'
        candidate.write_text(proposed)
        original.write_text(collapse(actual))
        setup = strict_setup(out/'setup.tcl', setup_file)
        process = subprocess.run(['netgen', '-batch', 'lvs', f'{candidate} {NAME}',
            f'{original} {legacy.base.NAME}', str(setup), str(out/'lvs.log')], cwd=out, capture_output=True, text=True)
        (out/'lvs_console.log').write_text(process.stdout+process.stderr)
        if not clean_match((out/'lvs.log').read_text(), process.returncode):
            raise ValueError('Physical 23-role reference differs from passed shunted native counter')
        if any(sha(ROOT/n) != h for n, h in inputs.items()):
            raise ValueError('Native counter integration inputs changed during preflight')
        result = dict(native_parameters=parameters, counter_native_mos=744, counter_native_mims=51,
            downstream_native_mos=64, downstream_native_mims=6, harness_native_mos=808, harness_native_mims=57,
            all_twelve_native_boundaries_independently_replayed=True,
            strict_native_topology_equivalence_passed=True, counter_materials_compatible=True,
            new_counter_geometry_qualified=False, whole_counter_shared_wire_rc_qualified=False,
            counter_timing_qualified=False, all_pvt_covered=False, qualified_phy=False, scope=SCOPE)
        result['files'] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != 'state.json'}
        atomic(out/'summary.json', result)
        atomic(out/'state.json', dict(status='complete', passed=True, qualified_phy=False))
    except Exception as error:
        atomic(out/'state.json', dict(status='failed', error=str(error), qualified_phy=False))
        raise
    return out


if __name__ == '__main__':
    print(run(), flush=True)
