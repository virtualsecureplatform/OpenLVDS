#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only DLL integration preflight; no simulation, staging or PHY admission."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import re
import sys

import benchmark_ltra_exact_tx as benchmark
import probe_driver_compact_native as pilot
import qualify_dll_storage as storage
import restore_compensated_coupled as restoration
from dll_campaign import bias_reference_count
from selected_phy import pins
from spice_probes import ProbeNetwork
from spice_scope import closure_hash
from stage_phy_candidate import overlay

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = ('lvds_bias', 'openlvds_driver_core', 'openlvds_receiver_core',
             'openlvds_tx_core', 'openlvds_ddr_rx')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dll_context(qualification):
    """Validate the exact storage producer profile, without executing a case."""
    if not qualification.is_relative_to(ROOT / 'build/diagnostics/dll_qualification'):
        raise ValueError('Require an isolated corrected DLL qualification')
    m = json.loads((qualification / 'manifest.json').read_text())
    a = json.loads((qualification / 'storage_source_admission.json').read_text())
    if (m['identity'].get('variant') != storage.VARIANT or a.get('variant') != storage.VARIANT or
            a.get('manifest_sha256') != sha(qualification / 'manifest.json') or
            a.get('producer_sha256') != sha(Path(storage.__file__)) or not a.get('proofs') or
            any(sha(ROOT / n) != h for n, h in a['proofs'].items())):
        raise ValueError('Corrected DLL source admission changed')
    with storage.profile():
        storage.native.validate(qualification, m)
    return (qualification / 'full.spice').read_text()


def compose(base, driver, receiver, dll, deck):
    if closure_hash(base, 'openlvds_receiver_core') != closure_hash(receiver, 'openlvds_receiver_core'):
        raise ValueError('Reference does not use the admitted preferred receiver')
    lib = restoration.substitute(base, driver, deck)
    if pins(lib, 'openlvds_dll') != pins(dll, 'openlvds_dll'):
        raise ValueError('Corrected DLL changes its public terminal order')
    lib = overlay(lib, dll, 'openlvds_dll', PROTECTED)
    printed = re.findall(r'(?im)^\.print tran[^\n]+', deck)
    if len(printed) != 1:
        raise ValueError('Require one captured diagnostic print statement')
    probes = re.findall(r'V\(([^)]+)\)', printed[0])
    ProbeNetwork(lib).validate(deck, probes)
    if bias_reference_count(deck, lib) != 2:
        raise ValueError('Require one native bias reference per diagnostic endpoint')
    return lib, dict(dll_ports=pins(lib, 'openlvds_dll'),
        driver_ports=pins(lib, 'openlvds_driver_core'),
        receiver_ports=pins(lib, 'openlvds_receiver_core'), probes=len(probes),
        diagnostic_endpoint_bias_references=2,
        protected_closures={n: closure_hash(lib, n) for n in PROTECTED})


def check(native_pilot, reference, receiver_rc, qualification):
    # Only completed pilot/reference/receiver evidence is remeasured. The DLL
    # full campaign may still be running: its immutable inputs, not its partial
    # output or electrical qualification, are used by this preflight.
    report = pilot.verify(native_pilot)
    pm = pilot.bound(native_pilot)
    if (report.get('native_output_pilot_passed') is not True or
            pm['identity'].get('view') != 'native_core_and_native_bias' or
            'source_readiness' not in pm['identity']):
        raise ValueError('Require complete compensated native core/bias pilots')
    benchmark.context(reference)
    comparison = benchmark.compare(reference)
    if json.loads(comparison.read_text()).get('exact_tx_comparison_passed') is not True:
        raise ValueError('Require the complete exact-TX numerical comparison')
    restoration.receiver_gate(receiver_rc)
    model = (native_pilot / 'tt_25_negative_op/source.spice').read_text()
    if any((native_pilot / t['id'] / 'source.spice').read_text() != model for t in pm['tasks']):
        raise ValueError('Native pilot cases select different driver models')
    dll = dll_context(qualification)
    lib, result = compose((reference / 'library.spice').read_text(), model,
        (receiver_rc / 'full.library.spice').read_text(), dll, (reference / 'bench.cir').read_text())
    paths = [native_pilot / n for n in ['manifest.json', 'summary.json']]
    paths += [reference / n for n in ['manifest.json', 'comparison.json', 'library.spice', 'bench.cir']]
    paths += [receiver_rc / n for n in ['manifest.json', 'summary.json', 'full.library.spice']]
    paths += [qualification / n for n in ['manifest.json', 'storage_source_admission.json', 'full.spice']]
    paths += [ROOT / 'scripts' / n for n in [Path(__file__).name, 'qualify_dll_storage.py',
        'qualify_dll_candidate.py', 'restore_compensated_coupled.py', 'stage_phy_candidate.py']]
    return dict(preflight_passed=True, **result,
        composed_library_sha256=hashlib.sha256(lib.encode()).hexdigest(),
        context_files={str(p.relative_to(ROOT)): sha(p) for p in paths},
        physical_admission=False, native_matrix_admission=False, dll_electrical_admission=False,
        qualified_phy=False, selected_library_written=False,
        scope='Read-only composition of compensated native pilot driver, admitted preferred receiver, '
        'exact TX/capture and storage-corrected DLL inputs. All diagnostic probes and two existing '
        'endpoint references preserved. DLL is not instantiated in this ideal-phase diagnostic; '
        'this proves library compatibility only, not a combined DLL/TX bias arrangement, measured '
        'phase replay, startup, timing margin, full PVT, stability, RC certification or PHY release.')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('native_pilot', type=Path)
    p.add_argument('reference', type=Path)
    p.add_argument('receiver_rc', type=Path)
    p.add_argument('qualification', type=Path)
    a = p.parse_args(argv)
    # Cached validators may print progress paths. Keep the report a single
    # JSON document without suppressing those diagnostics.
    with redirect_stdout(sys.stderr):
        report = check(*(v.resolve() for v in [a.native_pilot, a.reference,
            a.receiver_rc, a.qualification]))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
