#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Matched short/payload restoration after complete native and component gates."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import assemble_driver_compact_native as assembly
import benchmark_ltra_exact_tx as benchmark
import qualify_driver_compact_components as components
import qualify_driver_compact_native as native
import receiver_spec_screen as receiver
import recover_baseline_payload as baseline
import validate_receiver_spec_rc as receiver_rc
from dll_campaign import atomic, bias_reference_count, text_block
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_library import replace
from spice_probes import ProbeNetwork
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
TOP = assembly.TOP
NAMESPACE = 'compensated_coupled_restoration'
sha = assembly.sha


def completed_inputs(folder, manifest):
    paths = [folder / 'manifest.json', folder / 'summary.json']
    for task in manifest['tasks']:
        child = folder / task['id']
        row = json.loads((child / 'summary.json').read_text())
        paths += [child / n for n in set(task['files']) | set(row['files']) | {'summary.json'}]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def driver_gate(matrix, component):
    output = native.verify(matrix)
    if (output.get('native_output_matrix_passed') is not True or output.get('required_cases') != 30
            or output.get('required_pvt') != 15 or output.get('passed_pvt') != 15):
        raise ValueError('Require the complete passing thirty-case native output matrix')
    long = components.verify(component)
    if long.get('passed') is not True or long.get('required') != 30 or long.get('passed_cases') != 30:
        raise ValueError('Require all thirty passing long component fixtures')
    nm, cm = native.bound(matrix), components.bound(component)
    if nm['identity']['pilot'] != cm['identity']['pilot']:
        raise ValueError('Native output and long component campaigns select different pilots')
    pm = native.pilot.bound(ROOT / nm['identity']['pilot'])
    pi = pm['identity']
    if (pi.get('view') != 'native_core_and_native_bias' or 'source_readiness' not in pi
            or pi.get('assembly') != cm['identity']['assembly']):
        raise ValueError('Require the same compensated native core and native bias assembly')
    assembled = ROOT / pi['assembly']
    a = json.loads((assembled / 'summary.json').read_text())
    if assembly.assemble(ROOT / a['identity']['extraction']) != assembled:
        raise ValueError('Native assembly changed')
    model = (assembled / 'native.spice').read_text()
    if any((matrix / t['id'] / 'source.spice').read_text() != model for t in nm['tasks']):
        raise ValueError('Native output cases differ from the audited assembly')
    views = {'native': model, 'schematic': (assembled / 'schematic.spice').read_text()}
    if any((component / t['id'] / 'source.spice').read_text() != views[t['view']] for t in cm['tasks']):
        raise ValueError('Long component cases differ from the audited assembly')
    inputs = {**nm['identity']['inputs'], **cm['identity']['inputs'],
        **completed_inputs(matrix, nm), **completed_inputs(component, cm)}
    inputs[str((assembled / 'summary.json').relative_to(ROOT))] = sha(assembled / 'summary.json')
    code = {**nm['identity']['code'], **cm['identity']['code']}
    return model, inputs, code


def substitute(base, model, deck):
    def ports(text):
        match = re.search(r'(?im)^\.subckt[ \t]+' + TOP + r'\b[^\n]*(?:\n\+[^\n]*)*', text)
        if match is None:
            raise ValueError('Missing driver interface')
        return match[0].replace('\n+', ' ').split()[2:]
    if ports(base) != ports(model) or closure_hash(base, 'lvds_bias') != closure_hash(model, 'lvds_bias'):
        raise ValueError('Driver substitution changes the interface or exact native bias')
    result = replace(base, TOP, text_block(model, TOP))
    for name in ['lvds_bias', 'openlvds_tx_core', 'openlvds_receiver_core', 'openlvds_ddr_rx']:
        if closure_hash(base, name) != closure_hash(result, name):
            raise ValueError('Driver substitution changed unrelated circuit ' + name)
    if bias_reference_count(deck, result) != 2:
        raise ValueError('Require one shared reference per TX/RX endpoint')
    for line in ['IREF_TX IREF_TX 0 35u', 'IREF_RX IREF_RX 0 35u']:
        if deck.splitlines().count(line) != 1:
            raise ValueError('Endpoint reference source changed')
    probes = re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0])
    ProbeNetwork(result).validate(deck, probes)
    return result


def fixture(deck, old, new, stop):
    include = f'.include "{old}/library.spice"'
    if (deck.count(include) != 1 or re.findall(r'(?im)^\.tran[^\n]+', deck) != ['.tran 1p 188.049n 0 1p']
            or stop not in [12, 188.049]):
        raise ValueError('Require the unchanged original full diagnostic fixture')
    return deck.replace(include, f'.include "{new}/library.spice"').replace(
        '.tran 1p 188.049n 0 1p', f'.tran 1p {stop}n 0 1p')


def receiver_gate(rx):
    m = json.loads((rx / 'manifest.json').read_text())
    r = json.loads((rx / 'summary.json').read_text())
    if (r.get('receiver_rc_passed') is not True or r.get('manifest_sha256') != sha(rx / 'manifest.json')
            or receiver_rc.prepare(ROOT / m['identity']['campaign']) != rx):
        raise ValueError('Require the admitted preferred receiver components and RC context')
    results, proofs = [], {}
    for mode, label in [('full', 'reference'), ('fast', 'approximation')]:
        saved = r['case'][label]
        folder = ROOT / saved['artifact']
        if not folder.is_relative_to(ROOT / 'build/rc_validation/ngspice/receiver'):
            raise ValueError('Require the captured receiver RC traces')
        evidence = receiver_rc.original.shared.rc_trace.verified(folder, engine(),
            m['identity']['simulator_provenance'], sha(ROOT / 'requirements.json'), saved['trace_evidence_sha256'])
        if (evidence is None or evidence['scope_sha256'] != saved['scope_sha256']
                or evidence['inputs'] != m[mode + '_inputs']):
            raise ValueError('Receiver RC comparison trace changed or incomplete')
        wave, _ = baseline.original.read_wave(folder / 'bench.cir.prn')
        results.append((folder, None, wave, evidence['inputs'], saved))
        proofs[str((folder / 'trace_evidence.json').relative_to(ROOT))] = sha(folder / 'trace_evidence.json')
        proofs.update({str((folder / n).relative_to(ROOT)): h for n, h in evidence['files'].items()})
    compared = receiver_rc.original.validation.compare('receiver', *results)
    if compared != r['case'] or compared.get('passed') is not True:
        raise ValueError('Independent receiver RC comparison changed')
    return m, proofs


def prepare(matrix, component, reference, rx):
    if engine() != 'ngspice':
        raise ValueError('Use pinned ngspice')
    model, inputs, code = driver_gate(matrix, component)
    bm = benchmark.context(reference)
    comparison = benchmark.compare(reference)
    compared = json.loads(comparison.read_text())
    if compared.get('exact_tx_comparison_passed') is not True:
        raise ValueError('Require the completed exact-TX numerical comparison')
    rm, receiver_proofs = receiver_gate(rx)
    base, deck = (reference / 'library.spice').read_text(), (reference / 'bench.cir').read_text()
    if closure_hash(base, 'openlvds_receiver_core') != closure_hash(
            (rx / 'full.library.spice').read_text(), 'openlvds_receiver_core'):
        raise ValueError('Coupled receiver differs from the qualified preferred native model')
    model = substitute(base, model, deck)
    inputs.update(bm['identity']['inputs'])
    inputs.update(rm['identity']['inputs'])
    inputs.update(receiver_proofs)
    inputs.update(compared['files'])
    paths = [reference / n for n in ['manifest.json', 'summary.json', 'comparison.json', 'bench.cir', 'library.spice']]
    paths += [rx / n for n in ['manifest.json', 'summary.json', 'full.library.spice']]
    paths += [ROOT / 'requirements.json', ROOT / 'receiver_acceptance.json']
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    code.update(bm['identity']['code'])
    code.update(rm['identity']['code'])
    code.update({n: sha(ROOT / 'scripts' / n) for n in [Path(__file__).name,
        'qualify_driver_compact_components.py', 'qualify_driver_compact_native.py',
        'benchmark_ltra_exact_tx.py', 'recover_baseline_payload.py', 'validate_receiver_spec_rc.py',
        'receiver_spec_screen.py', 'spice_probes.py', 'spice_scope.py', 'spice_dispatch.py', 'spice_engine.py']})
    identity = dict(native_matrix=str(matrix.relative_to(ROOT)), components=str(component.relative_to(ROOT)),
        reference=str(reference.relative_to(ROOT)), receiver_rc=str(rx.relative_to(ROOT)),
        inputs=inputs, code=code, simulator=provenance(), scope=
        'Change only the fully native/PVT/long-component-qualified compensated driver '
        'in the validated exact-TX/preferred-r2/native-capture/LTRA fixture. Preserve '
        'rails, one 35 uA shared reference per endpoint, channel, package/load, '
        'SS40/410 MHz/duty/skew/jitter, observations, original ideal quarter-phase, '
        '60 ns training and 32-bit payload. Fresh 12 ns numerical screen before '
        '188.049 ns payload and one-to-one clock transport/valid-level pulse checks. '
        'Diagnostic only: real DLL, at least 256 training cycles, long payloads, '
        'aperture-subtracted margin, full link conditions and PHY release remain open.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    tasks = []
    for name, stop in [('short', 12), ('payload', 188.049)]:
        folder = out / name
        folder.mkdir(exist_ok=True)
        for filename, body in [('library.spice', model), ('bench.cir', fixture(deck, reference, folder, stop))]:
            path = folder / filename
            if path.exists() and path.read_text() != body:
                raise ValueError('Prepared compensated coupled diagnostic changed')
            if not path.exists():
                path.write_text(body)
        tasks.append(dict(id=name, stop_ns=stop, files={n: sha(folder / n) for n in ['library.spice', 'bench.cir']}))
    capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return out


def context(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Use the isolated compensated coupled diagnostic')
    m = json.loads((out / 'manifest.json').read_text())
    i = m['identity']
    if (out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or provenance() != i['simulator']
            or i['code'].get(Path(__file__).name) != sha(Path(__file__))
            or [(t['id'], t['stop_ns']) for t in m['tasks']] != [('short', 12), ('payload', 188.049)]
            or any(sha(ROOT / n) != h for n, h in i['inputs'].items())
            or any(sha(ROOT / 'scripts' / n) != h for n, h in i['code'].items())
            or any(set(t['files']) != {'library.spice', 'bench.cir'} for t in m['tasks'])
            or any(sha(out / t['id'] / n) != h for t in m['tasks'] for n, h in t['files'].items())
            or (out / 'short/library.spice').read_bytes() != (out / 'payload/library.spice').read_bytes()):
        raise ValueError('Compensated coupled evidence changed')
    return m


def payload(folder):
    metrics, transport = baseline.payload_metrics(folder)
    wave, h = baseline.completed_export(folder, 188.049)
    t = wave[:, 1]
    widths = receiver.valid_widths(t, wave[:, h['V(RXCLOCK)']], 60e-9, 120e-9)
    lo, hi = receiver.policy()['pin_range_v']
    pins = wave[:, [h['V(' + n + ')'] for n in ['RP', 'RN', 'RCP', 'RCN']]]
    minimum = receiver.policy()['native_screen']['minimum_valid_pulse_ps']
    pulses = transport['pulses']
    passed = (metrics.get('passed') is True and len(pulses) >= 40
        and all(sum(p['polarity'] == polarity for p in pulses) >= 20 for polarity in ['rising', 'falling'])
        and all(p['output_edges_in_next_input_period'] == 1 for p in pulses)
        and set(widths) == {'high', 'low'}
        and all(p['count'] >= 20 and p['minimum_ps'] >= minimum for p in widths.values())
        and pins.min() >= lo - 1e-9 and pins.max() <= hi + 1e-9)
    return dict(payload=metrics, clock_transport=transport, clock_valid_widths=widths,
        pin_range_v=[float(pins.min()), float(pins.max())], payload_restored=bool(passed),
        actual_dll_phase_qualified=False, training_cycles_qualified=False, sampling_margin_qualified=False)


def run(out):
    m = context(out)
    stamp = sha(out / 'manifest.json')
    def unchanged():
        context(out)
        if sha(out / 'manifest.json') != stamp:
            raise ValueError('Coupled manifest changed during execution')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists()
                for t in m['tasks'] for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log', 'summary.json']):
            raise ValueError('Prior or partial coupled output retained')
        rows = []
        for task in m['tasks']:
            folder = out / task['id']
            atomic(out / 'state.json', dict(status='waiting_for_' + task['id'], qualified_phy=False))
            error = result = measurements = None
            numerical = False
            try:
                with lease(ROOT, priority=2, label='compensated_coupled_' + task['id']):
                    unchanged()
                    atomic(out / 'state.json', dict(status='running_' + task['id'], qualified_phy=False))
                    result = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                        cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(result.stdout + result.stderr)
                result.check_returncode()
                unchanged()
                baseline.completed_export(folder, task['stop_ns'])
                numerical = True
                if task['id'] == 'payload':
                    measurements = payload(folder)
            except Exception as caught:
                error = str(caught)
            row = dict(task=task['id'], returncode=None if result is None else result.returncode,
                numerically_completed=numerical, error=error, measurements=measurements,
                manifest_sha256=stamp, qualified_phy=False, files={n: sha(folder / n) for n in
                    ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'] if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', row)
            rows.append(row)
            if error is not None:
                break
        unchanged()
        restored = len(rows) == 2 and rows[-1]['error'] is None and rows[-1]['measurements']['payload_restored']
        capture_manifest(out / 'summary.json', dict(results=rows, payload_restored=restored,
            manifest_sha256=stamp, qualified_phy=False, scope=m['identity']['scope']))
        atomic(out / 'state.json', dict(status='completed_payload_diagnostic' if restored
            else 'held_for_diagnosis', qualified_phy=False))


def verify(out):
    m = context(out)
    stamp = sha(out / 'manifest.json')
    rows = []
    for task in m['tasks']:
        folder = out / task['id']
        row = json.loads((folder / 'summary.json').read_text())
        if (row.get('task') != task['id'] or row.get('returncode') != 0
                or row.get('error') is not None or row.get('numerically_completed') is not True
                or row.get('manifest_sha256') != stamp
                or set(row['files']) != {'bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'}
                or any(sha(folder / n) != h for n, h in row['files'].items())):
            raise ValueError('Require unchanged complete coupled outputs')
        baseline.completed_export(folder, task['stop_ns'])
        measured = payload(folder) if task['id'] == 'payload' else None
        if measured != row['measurements']:
            raise ValueError('Coupled diagnostic remeasurement changed')
        rows.append(row)
    expected = dict(results=rows, payload_restored=rows[-1]['measurements']['payload_restored'],
        manifest_sha256=stamp, qualified_phy=False, scope=m['identity']['scope'])
    if expected != json.loads((out / 'summary.json').read_text()):
        raise ValueError('Coupled diagnostic aggregate changed')
    context(out)
    if sha(out / 'manifest.json') != stamp:
        raise ValueError('Coupled manifest changed during verification')
    return expected


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run', 'verify'])
    p.add_argument('artifact', type=Path)
    p.add_argument('--components', type=Path)
    p.add_argument('--reference', type=Path)
    p.add_argument('--receiver-rc', type=Path)
    args = p.parse_args()
    if args.action == 'prepare':
        if args.components is None or args.reference is None or args.receiver_rc is None:
            p.error('--components, --reference and --receiver-rc required')
        print(prepare(args.artifact.resolve(), args.components.resolve(), args.reference.resolve(),
            args.receiver_rc.resolve()), flush=True)
    elif args.action == 'run':
        run(args.artifact.resolve())
    else:
        result = verify(args.artifact.resolve())
        print(json.dumps(dict(verified=True, payload_restored=result['payload_restored'], qualified_phy=False)), flush=True)
