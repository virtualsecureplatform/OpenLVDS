#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rebind an unchanged analog GDS to a PFD-only source update, with fresh RC LVS."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from layout import circuits, flatten, schematic_text
from spice_library import checked_netlist, replace

ROOT = Path(__file__).resolve().parents[1]
TOP = 'openlvds_dll_analog'
CODE = ['rebind_dll_pfd_source.py', 'layout.py', 'lvs_utils.py', 'spice_library.py',
        'spice_scope.py', 'dll_candidate_rc.py', 'audit_rc.py', 'extract.py', 'reduce_rc.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n'); temp.replace(path)


def compatible(previous, proposed):
    before = circuits(previous); after = circuits(proposed)
    for source, definitions in [(previous, before), (proposed, after)]:
        if len(re.findall(r'(?im)^\.subckt\s+', source)) != len(definitions):
            raise ValueError('Duplicate source subcircuit')
    if set(before) != set(after) or 'lvds_pfd' not in before:
        raise ValueError('Source definitions changed')
    if before['lvds_pfd'][0] != after['lvds_pfd'][0]:
        raise ValueError('PFD public interface changed')
    if previous == proposed:
        raise ValueError('No PFD source update to bind')
    if replace(previous, 'lvds_pfd', 'PFD_SOURCE_PLACEHOLDER') != replace(proposed, 'lvds_pfd', 'PFD_SOURCE_PLACEHOLDER'):
        raise ValueError('Changes outside the PFD definition require a new analog layout')
    ports, devices = flatten(before, TOP)
    new_ports, new_devices = flatten(after, TOP)
    old_scope = schematic_text(TOP, ports, devices)
    new_scope = schematic_text(TOP, new_ports, new_devices)
    if ports != new_ports or old_scope != new_scope:
        raise ValueError('Analog schematic changed')
    return new_scope, ports


def prepare(base, source):
    base = base.resolve(); source = source.resolve()
    if not base.is_relative_to(ROOT / 'build/diagnostics/dll_layout') or not source.is_relative_to(ROOT):
        raise ValueError('Use an isolated DLL layout and an OpenLVDS source')
    physical = json.loads((base / 'summary.json').read_text())
    info = json.loads((base / 'extraction.json').read_text())
    audit = json.loads((base / 'rc_audit.json').read_text())
    old = base / 'candidate.spice'; previous = old.read_text(); proposed = source.read_text()
    scope, ports = compatible(previous, proposed)
    scope_sha = hashlib.sha256(scope.encode()).hexdigest()
    design = physical['designs'][TOP]; gds = ROOT / design['gds']
    if not physical['passed'] or digest(old) != physical['source_sha256']:
        raise ValueError('Parent physical source changed')
    if (scope_sha != design['lvs_source_sha256'] or scope_sha != info['source_scope_sha256'] or
            ports != info['ports'] or digest(gds.with_suffix('.sch.spice')) != scope_sha):
        raise ValueError('Parent GDS schematic scope changed')
    checked_netlist(info)
    if (digest(gds) != info['gds_sha256'] or info['source_sha256'] != physical['source_sha256'] or
            not audit['passed'] or audit['source_sha256'] != physical['source_sha256'] or
            audit['netlist_sha256'] != info['netlist_sha256'] or audit['gds_sha256'] != info['gds_sha256'] or
            digest(ROOT / audit['report']) != audit['report_sha256']):
        raise ValueError('Parent extraction or RC audit changed')
    inputs = [base / n for n in ['candidate.spice', 'summary.json', 'extraction.json', 'rc_audit.json']]
    inputs += [gds, gds.with_suffix('.sch.spice'), ROOT / info['netlist'], ROOT / audit['report'], source]
    identity = dict(parent=str(base.relative_to(ROOT)), source=str(source.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): digest(p) for p in inputs},
                    code={name: digest(ROOT / 'scripts' / name) for name in CODE},
                    previous_source_sha256=physical['source_sha256'], source_sha256=digest(source),
                    analog_scope_sha256=scope_sha, gds_sha256=info['gds_sha256'], netlist_sha256=info['netlist_sha256'],
                    changed_definition='lvds_pfd', electrical_qualification_transferred=False)
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    out = ROOT / 'build/diagnostics/dll_layout' / ('pfd_bind_' + fingerprint[:16])
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest_path = out / 'source_rebinding.json'
        if manifest_path.exists():
            saved = json.loads(manifest_path.read_text())
            if saved['identity'] != identity or any(digest(out / n) != h for n, h in saved['files'].items()):
                raise ValueError('Source binding evidence changed')
            if any(digest(out / 'producer_archive' / n) != h for n, h in identity['code'].items()):
                raise ValueError('Source binding producer archive changed')
            print(out, flush=True); return out
        archive = out / 'producer_archive'; archive.mkdir(exist_ok=True)
        for name in CODE:
            (archive / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
        (out / 'candidate.spice').write_text(proposed)
        (out / 'previous_candidate.spice').write_text(previous)
        (out / 'source_scope.spice').write_text(scope)
        summary = dict(physical, source_sha256=identity['source_sha256'], fingerprint=fingerprint,
                       source=str(source.relative_to(ROOT)), qualified_phy=False,
                       source_rebinding=dict(parent=identity['parent'], analog_scope_sha256=scope_sha,
                                             changed_definition='lvds_pfd', electrical_qualification_transferred=False))
        extraction = dict(info, source_sha256=identity['source_sha256'], qualified=False,
                          source_rebinding=dict(parent=str((base / 'extraction.json').relative_to(ROOT)),
                                                unchanged_gds=True, unchanged_extracted_network=True))
        atomic(out / 'summary.json', summary); atomic(out / 'extraction.json', extraction)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/dll_candidate_rc.py'), str(out)],
                                cwd=ROOT, capture_output=True, text=True)
        (out / 'independent_audit.log').write_text(result.stdout + result.stderr); result.check_returncode()
        new_info = json.loads((out / 'extraction.json').read_text()); new_audit = json.loads((out / 'rc_audit.json').read_text())
        if (new_info['netlist_sha256'] != identity['netlist_sha256'] or new_info['gds_sha256'] != identity['gds_sha256'] or
                not new_audit['passed'] or new_audit['source_sha256'] != identity['source_sha256'] or
                new_audit['schematic_sha256'] != scope_sha):
            raise ValueError('Fresh audit failed to preserve the analog scope/network')
        for name, value in identity['inputs'].items():
            if digest(ROOT / name) != value:
                raise ValueError('Source binding input changed')
        if identity['code'] != {name: digest(ROOT / 'scripts' / name) for name in CODE}:
            raise ValueError('Source binding producer changed')
        if any(digest(archive / n) != h for n, h in identity['code'].items()):
            raise ValueError('Source binding producer archive changed')
        atomic(manifest_path, dict(identity=identity, diagnostic=True, qualified_phy=False,
               scope='Only the unrelated PFD source definition changed; analog GDS/network unchanged; fresh strict RC LVS',
               files={n: digest(out / n) for n in ['candidate.spice', 'previous_candidate.spice', 'source_scope.spice',
                                                  'summary.json', 'extraction.json', 'rc_audit.json', 'independent_audit.log']}))
    print(out, flush=True); return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layout', type=Path); parser.add_argument('source', type=Path)
    args = parser.parse_args(); prepare(args.layout, args.source)
