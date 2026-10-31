#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare an audited Q-reset physical PFD with captured diagnostic fixtures."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

from digital_candidate_rc import captured_inputs
from dll_campaign import atomic, bias_reference_count
from dll_candidate_library import audited
from dll_measurements import average, column, complete, read_wave
from pfd_qreset_policy import pfd_qreset_paths_retained
from qualify_dll_candidate import validate
from spice_engine import command, provenance
from spice_library import checked_netlist, replace
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def library(reference, physical, ports):
    expected = {'REF', 'FB', 'RESET_N', 'PD_ENABLE', 'UP', 'DN', 'VGND', 'VPWR'}
    if len(ports) != 8 or set(ports) != expected:
        raise ValueError('Candidate PFD ports differ from the eight-terminal interface')
    physical, count = re.subn(r'(?im)^(\.subckt\s+)lvds_pfd\b', r'\1lvds_pfd_physical', physical)
    if count != 1:
        raise ValueError('Missing or ambiguous physical PFD header')
    physical = re.sub(r'(?im)^(\.ends\s+)lvds_pfd\b', r'\1lvds_pfd_physical', physical)
    mapping = dict(VPWR='VDDD', VGND='VSS')
    adapter = ('.subckt lvds_pfd REF FB RESET_N PD_ENABLE UP DN VDDD VSS\nXPHYS ' +
               ' '.join(mapping.get(p, p) for p in ports) + ' lvds_pfd_physical\n.ends lvds_pfd')
    return replace(replace(reference, 'lvds_pfd_physical', physical), 'lvds_pfd', adapter)


def physical_evidence(out):
    manifest = json.loads((out / 'summary.json').read_text())
    if manifest.get('pfd_policy') != 'pulse-area-q-reset' or captured_inputs(out, manifest) != 'lvds_pfd':
        raise ValueError('Expected a source-bound Q-reset physical candidate')
    for name, value in manifest['qreset_producer_code'].items():
        if digest(ROOT / 'scripts' / name) != value or digest(out / 'producer_archive' / name) != value:
            raise ValueError('Physical producer or archive changed')
    run = ROOT / manifest['run']; netlist = run / 'final/nl/lvds_pfd.nl.v'
    if not pfd_qreset_paths_retained(netlist.read_text()):
        raise ValueError('Physical Q-reset connectivity changed')
    info = json.loads((out / 'extraction.json').read_text()); audited(out, info)
    gds = run / 'final/gds/lvds_pfd.gds'
    if digest(gds) != info['gds_sha256'] or info['source_sha256'] != manifest['source_sha256']:
        raise ValueError('Physical PFD extraction is stale')
    proofs = [out / n for n in ['summary.json', 'extraction.json', 'rc_audit.json', 'preceding_policy_check.json']]
    proofs += [netlist, gds, ROOT / info['netlist']]
    if digest(out / 'preceding_policy_check.json') != manifest['preceding_policy_check_sha256']:
        raise ValueError('Preceding-policy evidence changed')
    return info, {str(p.relative_to(ROOT)): digest(p) for p in proofs}


def run(physical, reference):
    physical = physical.resolve(); reference = reference.resolve()
    if not physical.is_relative_to(ROOT / 'build/diagnostics') or not reference.is_relative_to(ROOT / 'build/diagnostics/pfd_capture'):
        raise ValueError('Use isolated physical and capture diagnostics')
    info, proofs = physical_evidence(physical)
    captured = json.loads((reference / 'manifest.json').read_text())
    if digest(ROOT / 'scripts/diagnose_pfd_capture.py') != captured['identity']['producer_sha256']:
        raise ValueError('Matched capture producer changed')
    qroot = ROOT / captured['identity']['qualification']
    q = json.loads((qroot / 'manifest.json').read_text()); validate(qroot, q)
    if digest(qroot / 'manifest.json') != captured['identity']['manifest_sha256']:
        raise ValueError('Reference native qualification changed')
    source = ROOT / q['identity']['full_models']['layout'] / 'candidate.spice'
    if (digest(qroot / 'full.spice') != captured['identity']['library_sha256'] or
            digest(source) != captured['identity']['source_sha256'] or
            provenance() != captured['identity']['simulator_provenance']):
        raise ValueError('Matched analog loading or simulator changed')
    tasks = [t for t in captured['tasks'] if t['view'] == 'native_rc_output_reset']
    if sorted(t['offset_ps'] for t in tasks) != [-850, 0, 850]:
        raise ValueError('Incomplete matched capture fixtures')
    identity = dict(physical=str(physical.relative_to(ROOT)), physical_proofs=proofs,
                    reference=str(reference.relative_to(ROOT)), reference_sha256=digest(reference / 'manifest.json'),
                    producer_sha256=digest(Path(__file__)), policy_sha256=digest(ROOT / 'scripts/pfd_qreset_policy.py'),
                    simulator_provenance=provenance())
    root = ROOT / 'build/diagnostics/pfd_physical_capture' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        generated = []
        for task in tasks:
            old = reference / task['id']; folder = root / str(task['offset_ps']); folder.mkdir(exist_ok=True)
            for name, value in task['files'].items():
                if digest(old / name) != value:
                    raise ValueError('Matched reference fixture changed')
            native = library((old / 'library.spice').read_text(), checked_netlist(info), info['ports'])
            deck = (old / 'bench.cir').read_text()
            previous_include = f'.include "{old}/library.spice"'
            if deck.count(previous_include) != 1:
                raise ValueError('Unexpected reference library inclusion')
            deck = deck.replace(previous_include, f'.include "{folder}/library.spice"')
            if bias_reference_count(deck, native) != 1:
                raise ValueError('Duplicate bias reference')
            ProbeNetwork(native).validate(deck, task['aliases'].values())
            for filename, text in [('library.spice', native), ('bench.cir', deck)]:
                path = folder / filename
                if path.exists() and path.read_text() != text:
                    raise ValueError('Captured candidate fixture changed')
                path.write_text(text)
            generated.append(dict(id=folder.name, aliases=task['aliases'], offset_ps=task['offset_ps'],
                                  files={n: digest(folder / n) for n in ['library.spice', 'bench.cir']}))
        atomic(root / 'manifest.json', dict(identity=identity, tasks=generated, qualified_phy=False,
               scope='Actual Q-reset GDS/extracted PFD, schematic analog/delay and extracted bias; no closed-loop or PHY qualification'))
        for task in generated:
            folder = root / task['id']; path = folder / 'summary.json'
            if path.exists():
                report = json.loads(path.read_text())
                if any(digest(folder / n) != value for n, value in report['files'].items()):
                    raise ValueError('Captured diagnostic evidence changed')
                continue
            atomic(folder / 'execution.json', dict(status='waiting_for_slot'))
            with slot():
                atomic(folder / 'execution.json', dict(status='running'))
                result = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'), cwd=folder, capture_output=True, text=True)
            (folder / 'console.log').write_text(result.stdout + result.stderr); result.check_returncode()
            wave, header = read_wave(folder / 'bench.cir.prn')
            if not complete(wave, 80):
                raise ValueError('Incomplete candidate capture trace')
            for alias, node in task['aliases'].items():
                header['V(' + alias.upper() + ')'] = header['V(' + node.upper() + ')']
            t = wave[:, 1]; keep = (t >= 60e-9) & (t <= 80e-9)
            means = {n: average(t[keep], column(wave, header, n)[keep]) for n in ['UP', 'DN', 'UF', 'DF']}
            difference = means['UP'] - means['DN']; offset = task['offset_ps']
            correct = difference * offset > 0 if offset else abs(difference) < .02
            _, current_proofs = physical_evidence(physical); validate(qroot, q)
            if current_proofs != proofs or digest(Path(__file__)) != identity['producer_sha256']:
                raise ValueError('Physical candidate or diagnostic producer changed')
            report = dict(diagnostic=True, qualified_phy=False, offset_ps=offset, means_v=means,
                          raw_difference_v=difference, correct_area_sign=bool(correct),
                          manifest_sha256=digest(root / 'manifest.json'),
                          files={n: digest(folder / n) for n in ['library.spice', 'bench.cir', 'bench.cir.prn', 'bench.raw']})
            atomic(path, report); atomic(folder / 'execution.json', dict(status='completed'))
            print(task['id'], difference, correct, flush=True)
    print(root, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('physical', type=Path); parser.add_argument('--reference', required=True, type=Path)
    args = parser.parse_args(); run(args.physical, args.reference)
