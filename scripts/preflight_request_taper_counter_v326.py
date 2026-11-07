#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build/check the native counter integration netlist before timing-gated routing.

This validates actual component materials and structural native equivalence.
It never admits a counter, creates its placement, or runs a transient.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import qualify_fast_clear_counter_rc_v268 as base
import build_repaired_clock_counter_v191 as assembly
import native_clock_components_v2 as native
import native_bank_inventory_v51 as inventory
from audit_rc_comments_v2 import collapse
from lvs_utils import strict_setup, clean_match
from probe_digital_dcc_v2 import atomic

ROOT = base.ROOT
VERSION = 'qualified-buffer-materials-and-full-junction-native-counter-preflight-v326.2'
CONTEXT = 'counter_buffer_material_preflight_v326'
NAME = 'openlvds_request_taper_counter_v326'
BASE = ROOT/'build/diagnostics/fast_clear_counter_rc_v268/d058dcd53f23d60f'
DUT = ROOT/'build/diagnostics/request_taper_counter_v317/a9021aae03b1ad1c'
REQUEST = ROOT/'build/diagnostics/request_taper_buffer_rc_v324/39c432524ec4f06d'
CLOCK = ROOT/'build/diagnostics/regular_clock_buffer_v325/9d3380b4eca0696f'
REQ = 'openlvds_request_taper_buffer_v323'
CLK = 'openlvds_regular_clock_buffer_v325'
ROLES = dict(request_driver=REQ, request_driver_parallel=REQ, clock_driver=CLK, clock_driver_parallel=CLK)
sha = base.sha
SCOPE = ('Actual qualified native buffer/body material compatibility, proposed 22-macro '
         'counter netlist and strict equivalence to v317 native component circuitry only; '
         'no new counter geometry/shared RC/transient/SS40/PVT/DCC/PHY admission')


def components():
    # The active science interpreter has NumPy; bound physical producers use
    # the pinned CAD interpreter. Preserve that separation without monkeypatches.
    code = '''import sys,json
from pathlib import Path
sys.path.insert(0,"scripts")
import qualify_request_taper_buffer_rc_v324 as request
import build_regular_clock_buffer_v325 as clock
rows=[]
for module,argument,flag in ((request,sys.argv[1],"request_buffer_local_rc_qualified"),(clock,sys.argv[2],"regular_clock_buffer_local_rc_qualified")):
    folder=Path(argument);identity=module.bound(folder);report=json.loads((folder/"summary.json").read_text())
    if (json.loads((folder/"state.json").read_text())!=dict(status="complete",passed=True,qualified_phy=False)
        or report.get(flag) is not True or any(module.sha(folder/n)!=h for n,h in report["files"].items())
        or any(module.sha(module.ROOT/n)!=h for n,h in report["extracted_files"].items())):
        raise ValueError("Qualified buffer output evidence changed")
    physical=module.ROOT/identity["parent"] if module is request else folder
    physical_report=json.loads((physical/"summary.json").read_text())
    rows.append(dict(folder=str(folder.relative_to(module.ROOT)),identity=identity,report=report,
        physical=str(physical.relative_to(module.ROOT)),physical_report=physical_report))
files=sorted({str(Path(m.__file__).resolve().relative_to(request.ROOT)) for m in list(sys.modules.values())
    if getattr(m,"__file__",None) and Path(m.__file__).resolve().parent==request.ROOT/"scripts"})
print(json.dumps(dict(rows=rows,code=files)))
'''
    result = subprocess.run([assembly.repaired.CAD, '-c', code, str(REQUEST), str(CLOCK)],
        cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def native_reference(cells, macros):
    blocks = []
    orders = {}
    for model, material in sorted(macros.items()):
        file = ROOT/material['folder']/(model+'.lvs.spice')
        text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', file.read_text())
        definitions = native.definitions(text)
        order, body = definitions[model+'_flat']
        # Use the actual fully characterized native extraction for every
        # macro, preserving supplied junctions across equal W/L classes.
        inventory.native_leaves(text, model+'_flat')
        orders[model] = order
        blocks += ['.subckt '+model+' '+' '.join(order), *[' '.join(w) for w in body], '.ends '+model]
    blocks += ['.subckt '+NAME+' '+' '.join(base.physical.PORTS)]
    for cell in cells:
        order = orders[cell['model']]
        if set(order) != set(cell['pins']):
            raise ValueError('Actual native macro/public pin set changed')
        blocks.append('X'+cell['name']+' '+' '.join(cell['pins'][p] for p in order)+' '+cell['model'])
    return '\n'.join(blocks+['.ends '+NAME, ''])


def run():
    original = base.bound(BASE)['identity']
    base_report = json.loads((BASE/'summary.json').read_text())
    if (json.loads((BASE/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or base_report.get('fast_clear_counter_shared_wire_rc_qualified') is not True
            or any(sha(BASE/n) != h for n, h in base_report['files'].items())
            or any(sha(ROOT/n) != h for n, h in base_report['extracted_files'].items())):
        raise ValueError('Require unchanged qualified base-counter native materials')
    parent = ROOT/original['parent']
    physical = json.loads((parent/'manifest.json').read_text())['identity']
    library = components()
    cells = deepcopy(physical['cells'])
    if len(cells) != 22 or len({c['name'] for c in cells}) != 22:
        raise ValueError('Require the original exact 22-macro phase logic')
    manifest = json.loads((DUT/'manifest.json').read_text())
    if any(sha(DUT/n) != h for n, h in manifest['libraries'].items()):
        raise ValueError('Actual v317 native component library changed')
    dut_text = (DUT/'cells.spice').read_text()+'\n'+(DUT/'pair.spice').read_text()
    definitions = native.definitions(dut_text)
    ports, body = definitions[base.NAME]
    calls = {w[0][1:]: w for w in body}
    if len(body) != 22 or set(calls) != {c['name'] for c in cells} or ports != base.physical.PORTS:
        raise ValueError('Actual v317 phase-logic coverage/ports changed')
    for cell in cells:
        name = cell['name']
        call = calls[name]
        expected = ('openlvds_request_taper_p10n8_p20n16_v317' if name.startswith('request_driver')
                    else 'openlvds_regular_buffer_p20n16_v306') if name in ROLES else cell['model']
        if call[-1] != expected or dict(zip(definitions[expected][0], call[1:-1])) != cell['pins']:
            raise ValueError('Native v317 phase logic or buffer role pins changed')
        if name in ROLES:
            if cell['model'] != 'openlvds_buf_8_o4_shunted_v2':
                raise ValueError('Original counter buffer role changed')
            cell['model'] = ROLES[name]
    if sum(c['name'] in ROLES for c in cells) != 4:
        raise ValueError('Require both parallel CLK and REQUEST roles')
    macros = {n: m for n, m in physical['macros'].items() if n in {c['model'] for c in cells}}
    paths = [BASE/n for n in ('manifest.json', 'summary.json', 'state.json', *base_report['files'])]
    paths += [ROOT/n for n in {*original['inputs'], *base_report['extracted_files']}]
    paths += [DUT/'manifest.json', DUT/'cells.spice', DUT/'pair.spice', parent/'manifest.json']
    paths += [ROOT/n for n in library['code']]
    for model, row in zip((REQ, CLK), library['rows']):
        folder, pf = ROOT/row['folder'], ROOT/row['physical']
        info = row['physical_report']['physical']
        gds = ROOT/info['gds']
        if gds.name != model+'.gds' or set(row['physical_report']['ports']) != {'A', 'X', 'VGND', 'VPWR'}:
            raise ValueError('Qualified buffer model/public interface changed')
        macros[model] = dict(folder=str(gds.parent.relative_to(ROOT)))
        paths += [folder/n for n in ('manifest.json', 'summary.json', 'state.json', *row['report']['files'])]
        paths += [ROOT/n for n in {*row['identity']['inputs'], *row['report']['extracted_files']}]
        paths += [pf/n for n in ('manifest.json', 'summary.json', 'state.json', *row['physical_report']['files'])]
    for model, material in macros.items():
        paths += [ROOT/material['folder']/(model+suffix) for suffix in ('.gds', '.sch.spice', '.lvs.spice', '.lef')]
    candidate = native_reference(cells, macros)
    _, proposed = inventory.native_leaves(candidate, NAME)
    _, actual = inventory.native_leaves(collapse(dut_text), base.NAME)
    parameters = inventory.compare_parameters(proposed, actual)
    mos = sum('fet_' in d['model'] for d in proposed)
    mims = sum('cap_mim' in d['model'] for d in proposed)
    if (mos, mims, len(proposed)) != (744, 50, 794):
        raise ValueError('Proposed actual native counter inventory changed')
    _, harness = inventory.native_leaves(collapse(dut_text), 'openlvds_static_phase_release_loaded_v2')
    if (sum('fet_' in d['model'] for d in harness), sum('cap_mim' in d['model'] for d in harness)) != (808, 56):
        raise ValueError('Original counter/downstream-load inventory changed')
    witness = assembly.native_master_witness(macros)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    paths += [Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl']
    inputs = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha(p) for p in sorted(set(paths))}
    identity = dict(version=VERSION, cells=cells, macros=macros, candidate_sha256=hashlib.sha256(candidate.encode()).hexdigest(),
                    inputs=inputs, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    atomic(out/'manifest.json', dict(identity=identity, qualified_phy=False))
    atomic(out/'state.json', dict(status='checking', qualified_phy=False))
    try:
        new = out/'proposed_counter.sch.spice'
        old = out/'v317_collapsed_reference.spice'
        new.write_text(candidate)
        old.write_text(collapse(dut_text))
        setup = strict_setup(out/'setup.tcl', Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        process = subprocess.run(['netgen', '-batch', 'lvs', f'{new} {NAME}', f'{old} {base.NAME}',
            str(setup), str(out/'lvs.log')], cwd=out, capture_output=True, text=True)
        (out/'lvs_console.log').write_text(process.stdout+process.stderr)
        if not clean_match((out/'lvs.log').read_text(), process.returncode):
            raise ValueError('Proposed counter does not preserve actual v317 native topology')
        if any(sha(ROOT/n if not Path(n).is_absolute() else Path(n)) != h for n, h in inputs.items()):
            raise ValueError('Counter material inputs changed during preflight')
        report = dict(native_master_witness=witness, native_parameters=parameters,
            buffer_roles={c['name']: c['model'] for c in cells if c['name'] in ROLES},
            counter_native_mos=744, counter_native_mims=50, downstream_native_mos=64, downstream_native_mims=6,
            harness_native_mos=808, harness_native_mims=56, phase_logic_and_public_pins_preserved=True,
            strict_native_topology_equivalence_passed=True, counter_materials_compatible=True,
            new_counter_geometry_qualified=False, whole_counter_shared_wire_rc_qualified=False,
            counter_timing_qualified=False, all_pvt_covered=False, electrical_qualification_passed=False,
            qualified_phy=False, scope=SCOPE)
        report['files'] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != 'state.json'}
        atomic(out/'summary.json', report)
        atomic(out/'state.json', dict(status='complete', passed=True, qualified_phy=False))
    except Exception as error:
        atomic(out/'state.json', dict(status='failed', error=str(error), qualified_phy=False))
        raise
    return out


if __name__ == '__main__':
    print(run(), flush=True)
