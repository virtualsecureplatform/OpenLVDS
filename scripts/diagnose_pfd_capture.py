#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare PFD capture polarity and reset taps; diagnostic, never qualification."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

from dll_campaign import atomic, bias_reference_count
from dll_design import native_block
from dll_measurements import average, column, complete, edges, read_wave
from qualify_dll_candidate import phase_fixture, validate
from spice_engine import command, provenance
from spice_library import replace
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reset_views(reference):
    # This reference combines the archived placed netlist with PDK transistor
    # cell definitions. It omits extracted interconnect and junction geometry.
    pattern = r'(?im)^Xcoincidence UP DN (.+sky130_fd_sc_hd__and2_4)\s*$'
    if len(re.findall(pattern, reference)) != 1:
        raise ValueError('Expected one output-tapped reset coincidence cell')
    for name in ['ref_ff/Q', 'fb_ff/Q']:
        if name not in reference:
            raise ValueError('Missing internal PFD flip-flop output')
    altered = re.sub(pattern, r'Xcoincidence ref_ff/Q fb_ff/Q \1', reference)
    result = {}
    for name, text in [('schematic_output_reset', reference), ('schematic_q_reset', altered)]:
        text, count = re.subn(r'(?im)^(\.subckt\s+)lvds_pfd\b', r'\1lvds_pfd_physical', text)
        if count != 1:
            raise ValueError('Missing or ambiguous schematic PFD header')
        result[name] = text
    return result


def run(qualification):
    qualification = qualification.resolve()
    if not qualification.is_relative_to(ROOT / 'build/diagnostics/dll_qualification'):
        raise ValueError('Use an isolated native qualification')
    q = json.loads((qualification / 'manifest.json').read_text()); validate(qualification, q)
    source = ROOT / q['identity']['full_models']['layout'] / 'candidate.spice'
    reference = ROOT / 'build/diagnostics/pfd_area_physical/rc_audit/reference.spice'
    # Native source and physical PFD/bias come from the same prepared library.
    full = (qualification / 'full.spice').read_text()
    full = replace(full, 'openlvds_dll_analog', native_block(source.read_text(), 'openlvds_dll_analog'))
    views = {'native_rc_output_reset': full}
    for name, text in reset_views(reference.read_text()).items():
        views[name] = replace(full, 'lvds_pfd_physical', text)
    identity = dict(qualification=str(qualification.relative_to(ROOT)),
                    manifest_sha256=digest(qualification / 'manifest.json'),
                    library_sha256=digest(qualification / 'full.spice'), source_sha256=digest(source),
                    pfd_reference_sha256=digest(reference), producer_sha256=digest(Path(__file__)),
                    simulator_provenance=provenance(), stop_ns=80, score_ns=[60, 80])
    root = ROOT / 'build/diagnostics/pfd_capture' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        native_task = next(t for t in q['tasks'] if t['id'] == 'phase_ss_0_150ps')
        template = (qualification / native_task['id'] / 'bench.cir').read_text()
        pdk = re.search(r'(?m)^\.lib "([^"\n]+)"', template)[1]
        tasks = []
        for offset in [-850, 850, 0]:
            for name, library in views.items():
                folder = root / (name + '_' + str(offset) + 'ps'); folder.mkdir(exist_ok=True)
                spec = dict(kind='phase', process='ss', temperature=0, mhz=400, offset_ps=offset,
                            reference_slew_ps=100, feedback_slew_ps=100, architecture='averaged_pfd_ota')
                body, probes, _, _ = phase_fixture(spec)
                deck = (f'OpenLVDS PFD capture DIAGNOSTIC {folder.name}\n.lib "{pdk}" ss\n'
                        f'.include "{folder}/library.spice"\n.options device temp=0\n'
                        '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
                        'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n' + body +
                        '.tran 5p 80n 0 20p\n.print tran ' +
                        ' '.join('V(' + n + ')' for n in probes.values()) + '\n.end\n')
                if bias_reference_count(deck, library) != 1:
                    raise ValueError('Capture diagnostic duplicates the bias reference')
                ProbeNetwork(library).validate(deck, probes.values())
                for filename, text in [('library.spice', library), ('bench.cir', deck)]:
                    path = folder / filename
                    if path.exists() and path.read_text() != text:
                        raise ValueError('Captured fixture changed')
                    path.write_text(text)
                tasks.append(dict(id=folder.name, view=name, offset_ps=offset, aliases=probes,
                                  files={n: digest(folder / n) for n in ['library.spice', 'bench.cir']}))
        atomic(root / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False,
               scope='Matched schematic reset experiment plus native-RC control; no physical Q-reset implementation'))
        for task in tasks:
            folder = root / task['id']; report = folder / 'summary.json'
            if report.exists():
                saved = json.loads(report.read_text())
                if any(digest(folder / n) != h for n, h in saved['files'].items()):
                    raise ValueError('Captured result changed')
                continue
            atomic(folder / 'execution.json', dict(status='waiting_for_slot'))
            with slot():
                atomic(folder / 'execution.json', dict(status='running'))
                result = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                                        cwd=folder, capture_output=True, text=True)
            (folder / 'console.log').write_text(result.stdout + result.stderr); result.check_returncode()
            wave, header = read_wave(folder / 'bench.cir.prn')
            if not complete(wave, 80):
                raise ValueError('Incomplete capture trace')
            for alias, node in task['aliases'].items():
                header['V(' + alias.upper() + ')'] = header['V(' + node.upper() + ')']
            t = wave[:, 1]; keep = (t >= 60e-9) & (t <= 80e-9)
            means = {n: average(t[keep], column(wave, header, n)[keep]) for n in ['UP', 'DN', 'UF', 'DF']}
            difference = means['UP'] - means['DN']; offset = task['offset_ps']
            correct = difference * offset > 0 if offset else abs(difference) < .02
            measured = dict(diagnostic=True, qualified_phy=False, view=task['view'], offset_ps=offset,
                            means_v=means, raw_difference_v=difference, correct_area_sign=bool(correct),
                            manifest_sha256=digest(root / 'manifest.json'),
                            files={n: digest(folder / n) for n in ['library.spice', 'bench.cir', 'bench.cir.prn', 'bench.raw']})
            validate(qualification, q)
            if digest(Path(__file__)) != identity['producer_sha256']:
                raise ValueError('Capture producer changed')
            atomic(report, measured); atomic(folder / 'execution.json', dict(status='completed'))
            print(task['id'], difference, correct, flush=True)
    print(root, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('qualification', type=Path)
    run(parser.parse_args().qualification)
