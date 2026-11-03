#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract a fresh repaired-PFD RC model and check strict transistor LVS.

The physical artifact remains immutable. Extraction and its audit live in a
new context; no source, routed-matching, loop or PHY admission is inferred.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import harden_slew_pfd as physical
import digital_candidate_rc as legacy
from audit_rc import collapse
from lvs_utils import clean_match, strict_setup
from reduce_rc import reduce_netlist
from spice_library import checked_netlist

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'slew_pfd_rc'
sha = physical.sha
PORTS = {'REF', 'FB', 'RESET_N', 'PD_ENABLE', 'UP', 'DN', 'VPWR', 'VGND'}
CODE = ('extract_slew_pfd.py', 'digital_candidate_rc.py', 'extract.py', 'reduce_rc.py',
        'audit_rc.py', 'lvs_utils.py', 'spice_library.py')


def tool_context():
    result = physical.tools()
    result['extraction_binaries'] = {}
    for name in ('magic', 'netgen'):
        path = shutil.which(name)
        if path is None: raise ValueError('Use the pinned --tools environment with Magic and Netgen')
        result['extraction_binaries'][path] = sha(Path(path))
    return result


def prepare(parent):
    report = physical.verify(parent)
    if report['passed'] is not True: raise ValueError('Complete passing PFD placement/routing before fresh extraction')
    m = physical.bound(parent); pdk = Path(os.environ['PDK_ROOT']) / 'sky130A'
    collateral = dict(m['identity']['collateral'])
    paths = dict(cells=pdk / 'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice',
                 setup=pdk / 'libs.tech/netgen/sky130A_setup.tcl',
                 magicrc=pdk / 'libs.tech/magic/sky130A.magicrc', tech=pdk / 'libs.tech/magic/sky130A.tech')
    collateral.update({str(p): sha(p) for p in paths.values()})
    inputs = dict(m['identity']['inputs'])
    bound_files = [parent / n for n in ('manifest.json', 'summary.json', *m['files'])]
    bound_files += physical.output_files(parent)
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in bound_files})
    code = dict(m['identity']['code'])
    code.update({n: sha(ROOT / 'scripts' / n) for n in CODE})
    i = dict(parent=str(parent.relative_to(ROOT)), inputs=inputs, code=code, collateral=collateral,
             pdk_files={n: str(p) for n, p in paths.items()}, tools=tool_context(),
             scope='Fresh native RC and strict transistor LVS for the actual repaired-PFD GDS. Exact degree-four resistor elimination only. Routed-RC matching and expanded native/loop/stability/PHY qualification remain required.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # The copied summary is explicitly the parent physical receipt used by
        # the unchanged extractor. strict_summary.json holds this stage's result.
        for name in ('summary.json', 'config.json'):
            physical.write_once(out / name, (parent / name).read_text())
        (out / 'producers').mkdir(exist_ok=True)
        for n in code: physical.write_once(out / 'producers' / n, (ROOT / 'scripts' / n).read_text())
        physical.capture_manifest(out / 'manifest.json', dict(identity=i, qualified_phy=False, physical_admission=False))
    return out


def bound(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; parent = ROOT / i['parent']
    if (not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE) or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
            m['qualified_phy'] is not False or m['physical_admission'] is not False or tool_context() != i['tools'] or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items()) or
            any(sha(Path(n)) != h for n, h in i['collateral'].items()) or
            any((out / n).read_bytes() != (parent / n).read_bytes() for n in ('summary.json', 'config.json'))):
        raise ValueError('Strict PFD RC context changed')
    return m


def extraction_directory(out):
    r = json.loads((out / 'summary.json').read_text())
    gds = ROOT / r['run'] / 'final/gds/lvds_pfd.gds'
    digest = hashlib.sha256(gds.read_bytes() + (ROOT / 'scripts/extract.py').read_bytes()).hexdigest()
    return ROOT / 'build/extracted' / digest[:16] / 'lvds_pfd', digest


def non_resistors(text):
    return [line.strip() for line in text.splitlines() if line.strip() and
            not line.lstrip().startswith('*') and not line.lstrip().lower().startswith('r')]


def model_evidence(out, pdk_files):
    r = json.loads((out / 'summary.json').read_text()); info = json.loads((out / 'extraction.json').read_text())
    audit = json.loads((out / 'rc_audit.json').read_text())
    if legacy.captured_inputs(out, r) != 'lvds_pfd': raise ValueError('Expected the captured PFD physical source')
    gds = ROOT / r['run'] / 'final/gds/lvds_pfd.gds'; netlist = checked_netlist(info)
    raw = ROOT / info['raw_netlist']; native = ROOT / info['netlist']
    _, fingerprint = extraction_directory(out)
    if (len(info['ports']) != 8 or set(info['ports']) != PORTS or
            info['fingerprint'] != fingerprint or info['gds_sha256'] != sha(gds) or
            info['source_sha256'] != r['source_sha256'] or info.get('returncode') != 0 or
            info['resistors'] <= 0 or info['capacitors'] <= 0 or
            audit['gds_sha256'] != info['gds_sha256'] or audit['netlist_sha256'] != info['netlist_sha256'] or
            audit['source_sha256'] != info['source_sha256'] or
            audit['report_sha256'] != sha(ROOT / audit['report'])):
        raise ValueError('Strict RC source, public interface or extraction evidence changed')
    if non_resistors(raw.read_text()) != non_resistors(netlist): raise ValueError('Reduction changed a device, capacitor or public terminal')
    with tempfile.TemporaryDirectory(prefix='openlvds-pfd-rc-verify-') as temp:
        destination = Path(temp) / 'reduced.spice'
        reduction = reduce_netlist(raw, destination)
        if reduction != info['reduction'] or destination.read_bytes() != native.read_bytes():
            raise ValueError('Exact resistor elimination no longer reproduces the native model')
        expected_setup = strict_setup(Path(temp) / 'setup.tcl', Path(pdk_files['setup'])).read_text()
    physical_spice = ROOT / r['run'] / 'final/spice/lvds_pfd.spice'
    cells = Path(pdk_files['cells']); reference = out / 'rc_audit/reference.spice'
    if (audit['physical_spice_sha256'] != sha(physical_spice) or audit['pdk_cells_sha256'] != sha(cells) or
            audit['reference_sha256'] != sha(reference) or
            reference.read_text() != legacy.reference_schematic(physical_spice.read_text(), cells.read_text()) or
            (out / 'rc_audit/wire_collapsed.spice').read_text() != collapse(netlist) or
            (out / 'rc_audit/setup.tcl').read_text() != expected_setup):
        raise ValueError('Strict LVS reference or setup changed')
    passed = audit.get('passed') is True and clean_match((ROOT / audit['report']).read_text())
    return dict(passed=bool(passed), strict_lvs_passed=bool(passed), native_rc_passed=True,
                exact_reduction_reproduced=True, ports=info['ports'], model=info,
                physical_admission=False, route_matching_verified=False, qualified_phy=False)


def output_files(out):
    paths = [out / n for n in ('extraction.json', 'rc_audit.json')]
    paths += list((out / 'rc_audit').rglob('*'))
    if (out / 'extraction.json').is_file():
        info = json.loads((out / 'extraction.json').read_text())
        paths += [ROOT / info[n] for n in ('netlist', 'raw_netlist')]
        paths += list((ROOT / info['raw_netlist']).parent.glob('*'))
    return sorted(set(p for p in paths if p.is_file()))


def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json'); parent = ROOT / m['identity']['parent']
    with (out / '.execution.lock').open('a+') as lock, (parent / '.execution.lock').open('a+') as parent_lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(parent_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        target, _ = extraction_directory(out)
        if target.exists() or any((out / n).exists() for n in ('state.json', 'extraction.json', 'rc_audit.json', 'rc_audit', 'strict_summary.json')):
            raise ValueError('Existing/partial PFD RC output retained; no retry')
        try:
            physical.atomic(out / 'state.json', dict(status='extracting_strict_rc', qualified_phy=False))
            rc = legacy.run(out)
            bound(out)
            if sha(out / 'manifest.json') != stamp: raise ValueError('Strict RC manifest changed')
            result = model_evidence(out, m['identity']['pdk_files'])
            result['passed'] = bool(result['passed'] and rc == 0)
            report = dict(result, execution_returncode=rc, manifest_sha256=stamp,
                          files={str(p.relative_to(ROOT)): sha(p) for p in output_files(out)})
            physical.capture_manifest(out / 'strict_summary.json', report)
            physical.atomic(out / 'state.json', dict(status='strict_rc_verified' if report['passed'] else 'held_strict_rc_failed', qualified_phy=False))
            return report
        except Exception as e:
            physical.atomic(out / 'state.json', dict(status='held_for_diagnosis', error=str(e), qualified_phy=False)); raise


def verify(out):
    m = bound(out); saved = json.loads((out / 'strict_summary.json').read_text())
    report = model_evidence(out, m['identity']['pdk_files'])
    report['passed'] = bool(report['passed'] and saved['execution_returncode'] == 0)
    report.update(execution_returncode=saved['execution_returncode'], manifest_sha256=sha(out / 'manifest.json'),
                  files={str(p.relative_to(ROOT)): sha(p) for p in output_files(out)})
    if report != saved: raise ValueError('Strict PFD RC receipt changed')
    bound(out); return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run', 'verify']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); result = globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
