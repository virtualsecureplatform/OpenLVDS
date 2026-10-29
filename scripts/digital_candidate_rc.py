#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract an isolated digital candidate and independently check its RC topology."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from audit_rc import collapse
from extract import extract
from lvs_utils import clean_match, strict_setup
from spice_library import checked_netlist

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def captured_inputs(out, manifest):
    """Check the exact ordered input archive written by harden.py."""
    archive = ROOT / manifest['input_archive']
    config = json.loads((archive / 'config.json').read_text())
    name = config['DESIGN_NAME']
    which = {'openlvds_tx_core': 'tx', 'lvds_pfd': 'pfd'}[name]
    files = [archive / Path(p).name for p in config['VERILOG_FILES']]
    files += [archive / f'{which}_blackboxes.v', archive / f'{which}.sdc', archive / 'config.json']
    stamp = hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()
    if not manifest.get('passed') or not manifest.get('interface_verified') or stamp != manifest['source_sha256']:
        raise ValueError('Digital physical flow or captured inputs are invalid')
    if (out / 'config.json').read_bytes() != (archive / 'config.json').read_bytes():
        raise ValueError('Digital physical configuration changed')
    return name


def reference_schematic(text, cells):
    """Replace GDS abstract cell entries with the PDK transistor definitions."""
    names = set(re.findall(r'(?im)^\.subckt\s+(\S+)', cells))
    pattern = r'(?ims)^\.subckt\s+(\S+)\s.*?^\.ends[^\n]*'
    kept = []
    for match in re.finditer(pattern, text):
        if match[1] in names:
            body = [s.strip() for s in match[0].splitlines()[1:-1] if s.strip() and not s.lstrip().startswith('*')]
            if body:
                raise ValueError('Expected an abstract cell entry: ' + match[1])
        else:
            kept.append(match[0])
    return cells + '\n' + '\n\n'.join(kept) + '\n'


def run(out):
    manifest = json.loads((out / 'summary.json').read_text())
    name = captured_inputs(out, manifest)
    gds = ROOT / manifest['run'] / 'final/gds' / (name + '.gds')
    extraction = out / 'extraction.json'
    info = json.loads(extraction.read_text()) if extraction.exists() else {}
    fingerprint = hashlib.sha256(gds.read_bytes() + Path(__file__).with_name('extract.py').read_bytes()).hexdigest()
    if not (info.get('passed') and info.get('fingerprint') == fingerprint and
            info.get('source_sha256') == manifest['source_sha256'] and info.get('gds_sha256') == digest(gds)):
        info = extract(name, gds, manifest['source_sha256'])
        extraction.write_text(json.dumps(info, indent=2) + '\n')
    netlist = checked_netlist(info)
    pdk = Path(os.environ['PDK_ROOT']) / 'sky130A'
    cell_file = pdk / 'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    physical_spice = ROOT / manifest['run'] / 'final/spice' / (name + '.spice')
    audit = out / 'rc_audit'
    audit.mkdir(exist_ok=True)
    collapsed = audit / 'wire_collapsed.spice'
    collapsed.write_text(collapse(netlist))
    reference = audit / 'reference.spice'
    reference.write_text(reference_schematic(physical_spice.read_text(), cell_file.read_text()))
    setup = strict_setup(audit / 'setup.tcl', pdk / 'libs.tech/netgen/sky130A_setup.tcl')
    report = audit / 'lvs.log'
    result = subprocess.run(['netgen', '-batch', 'lvs', f'{collapsed} {name}', f'{reference} {name}',
                             str(setup), str(report)], cwd=audit, capture_output=True, text=True)
    (audit / 'console.log').write_text(result.stdout + result.stderr)
    passed = clean_match(report.read_text() if report.exists() else '', result.returncode)
    summary = dict(passed=passed, source_sha256=manifest['source_sha256'], gds_sha256=digest(gds),
                   netlist_sha256=info['netlist_sha256'], physical_spice_sha256=digest(physical_spice),
                   pdk_cells_sha256=digest(cell_file), reference_sha256=digest(reference),
                   report=str(report.relative_to(ROOT)), report_sha256=digest(report) if report.exists() else None)
    (out / 'rc_audit.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    return 0 if passed else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('physical', type=Path)
    a = p.parse_args()
    out = a.physical.resolve()
    if not out.is_relative_to(ROOT / 'build/diagnostics'):
        p.error('Use an isolated physical directory in build/diagnostics')
    return run(out)


if __name__ == '__main__':
    raise SystemExit(main())
