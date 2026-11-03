#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Stage an exact-RC diagnostic PHY after restored payload and full native gates."""
import argparse
from contextlib import redirect_stdout
import fcntl
import hashlib
import json
from pathlib import Path
import sys

import dll_native_evidence
import preflight_compensated_dll as integration
import restore_compensated_coupled as restored
from digital_candidate_rc import captured_inputs
from dll_campaign import text_block
from dll_candidate_library import audited
from receiver_static_diagnosis import capture_manifest
from rx_candidate_aperture import audited_model
from spice_engine import provenance
from spice_library import checked_netlist, library
from spice_probes import ProbeNetwork
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'compensated_phy'
BLOCKS = {'openlvds_driver_core', 'openlvds_receiver_core', 'openlvds_dll_analog',
          'lvds_bias', 'lvds_pfd', 'openlvds_tx_core', 'openlvds_ddr_rx', 'openlvds_delay_line'}
DIGITAL = {'openlvds_tx_core', 'openlvds_ddr_rx'}
CODE = [Path(__file__).name, 'preflight_compensated_dll.py', 'dll_native_evidence.py',
        'digital_candidate_rc.py', 'dll_candidate_library.py', 'rx_candidate_aperture.py',
        'rx_candidate_rc.py', 'selected_phy.py', 'stage_phy_candidate.py', 'dll_campaign.py',
        'spice_engine.py', 'spice_library.py', 'spice_probes.py', 'spice_scope.py',
        'receiver_static_diagnosis.py']
FLAGS = dict(diagnostic=True, qualified=False, complete_phy_suite=False,
             approximate_transient_qualified=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(paths):
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def dll_gate(qualification):
    """Refuse incomplete science before invoking the read-only full verifier."""
    integration.dll_context(qualification)
    m = json.loads((qualification / 'manifest.json').read_text())
    tasks = m['tasks']; names = {t['id'] for t in tasks}
    if (len(tasks) != 336 or len(names) != 336 or
            not (qualification / 'summary.json').is_file() or
            any(not (qualification / n / 'summary.json').is_file() for n in names)):
        raise ValueError('Complete all 336 corrected native DLL cases before staging')
    r = json.loads((qualification / 'summary.json').read_text())
    if (r.get('passed') is not True or r.get('manifest_sha256') != sha(qualification / 'manifest.json') or
            set(r.get('tasks', {})) != names or
            any(t.get('status') != 'passed' for t in r['tasks'].values())):
        raise ValueError('Require a complete passing corrected DLL qualification')
    with integration.storage.profile():
        proof = dll_native_evidence.verify(qualification)
    paths = [qualification / n for n in ['manifest.json', 'summary.json',
             'storage_source_admission.json', 'full.spice', 'fast.spice', 'requirements.json']]
    paths += [qualification / n / f for n in names for f in
              ['summary.json', 'bench.cir', 'bench.raw', 'bench.cir.prn']]
    return m, proof, files(paths)


def match_model(lib, name, info):
    if text_block(lib, name) != text_block(checked_netlist(info), name):
        raise ValueError('Physical metadata differs from restored circuit: ' + name)


def driver_nodesets(lib, observations):
    """Use fresh GDS conductor labels rather than old schematic-name guesses."""
    values = {'SINK': 1.36, 'TOP': 2.42, 'DP': 0, 'DN': 3.3}
    names = [observations[n]['native_node'] for n in values]
    if len(set(names)) != len(names) or any(not n for n in names):
        raise ValueError('Driver observation conductors missing or merged')
    result = {inst + ':' + observations[n]['native_node']: v
              for inst in ['XDT', 'XCT'] for n, v in values.items()}
    # Only hierarchy/node existence is tested here. Actual voltages are Newton
    # guesses, not voltage sources, clamps or sampled stress substitutions.
    deck = '\n'.join(inst + ' D P N VR PB NB VA VD 0 openlvds_driver_core' for inst in ['XDT', 'XCT'])
    ProbeNetwork(lib).validate(deck, result)
    return result


def assemble(restoration, qualification, tx, rx):
    if not restoration.is_relative_to(ROOT / 'build/diagnostics' / restored.NAMESPACE):
        raise ValueError('Require the matched compensated coupled restoration')
    r = restored.verify(restoration)
    if r.get('payload_restored') is not True:
        raise ValueError('Restore complete ordered payload and clock transport before staging')
    cm = restored.context(restoration); ci = cm['identity']
    model, proofs, code = restored.driver_gate(ROOT / ci['native_matrix'], ROOT / ci['components'])
    qm, dll_proof, qp = dll_gate(qualification)
    proofs.update(qp)
    rm, receiver_proofs = restored.receiver_gate(ROOT / ci['receiver_rc'])
    proofs.update(receiver_proofs); proofs.update(rm['identity']['inputs'])
    proofs.update(ci['inputs']); code.update(ci['code']); code.update(qm['identity']['code'])
    proofs.update(restored.completed_inputs(restoration, cm))
    proofs.update(files([restoration / 'summary.json']))
    base = (restoration / 'payload/library.spice').read_text()
    rx_rc = ROOT / ci['receiver_rc']
    lib, compat = integration.compose(base, model, (rx_rc / 'full.library.spice').read_text(),
        (qualification / 'full.spice').read_text(), (restoration / 'payload/bench.cir').read_text())

    # Require the very same exact digital views that restored the chain.
    physical = json.loads((tx / 'summary.json').read_text())
    if captured_inputs(tx, physical) != 'openlvds_tx_core':
        raise ValueError('Require the explicit restored TX physical candidate')
    ti = json.loads((tx / 'extraction.json').read_text()); audited(tx, ti)
    ta = json.loads((tx / 'rc_audit.json').read_text())
    run = ROOT / physical['run']; archive = ROOT / physical['input_archive']
    config = json.loads((archive / 'config.json').read_text())
    gds = run / 'final/gds/openlvds_tx_core.gds'
    spice = run / 'final/spice/openlvds_tx_core.spice'
    reference = tx / 'rc_audit/reference.spice'
    if (sha(gds) != ti['gds_sha256'] or ti['source_sha256'] != physical['source_sha256'] or
            sha(spice) != ta['physical_spice_sha256'] or sha(reference) != ta['reference_sha256']):
        raise ValueError('Restored TX physical extraction changed')
    ri, rx_proofs = audited_model(rx)
    for name, info in [('openlvds_tx_core', ti), ('openlvds_ddr_rx', ri)]:
        match_model(lib, name, info)
    proofs.update(rx_proofs)
    proofs.update(files([tx / n for n in ['summary.json', 'extraction.json', 'rc_audit.json', 'config.json']]))
    proofs.update(files([gds, spice, reference, ROOT / ta['report'],
        run / 'final/nl/openlvds_tx_core.nl.v', archive / 'config.json',
        archive / 'tx_blackboxes.v', archive / 'tx.sdc'] +
        [archive / Path(n).name for n in config['VERILOG_FILES']]))

    nm = restored.native.bound(ROOT / ci['native_matrix'])
    pm = restored.native.pilot.bound(ROOT / nm['identity']['pilot'])
    assembly = ROOT / pm['identity']['assembly']
    a = json.loads((assembly / 'summary.json').read_text())
    driver = json.loads((ROOT / a['identity']['extraction'] / 'summary.json').read_text())['extraction']
    receiver = json.loads((ROOT / rm['identity']['layout'] / 'extraction.json').read_text())
    dll_models = qm['identity']['full_models']
    dll = json.loads((ROOT / dll_models['layout'] / 'extraction.json').read_text())
    pfd = json.loads((ROOT / dll_models['pfd'] / 'extraction.json').read_text())
    dl = json.loads((ROOT / dll_models['layout'] / 'summary.json').read_text())
    pf = json.loads((ROOT / dll_models['pfd'] / 'summary.json').read_text())
    dg = ROOT / dl['designs']['openlvds_dll_analog']['gds']
    pg = ROOT / pf['run'] / 'final/gds/lvds_pfd.gds'
    if sha(dg) != dll['gds_sha256'] or sha(pg) != pfd['gds_sha256']:
        raise ValueError('Qualified DLL/PFD GDS changed')
    proofs.update(files([dg, pg]))
    # Canonical bias/delay metadata must describe the actual frozen restored
    # bodies. This does not select a driver or receiver through active pointers.
    library(extracted=True, designs={'lvds_bias', 'openlvds_delay_line'})
    active = json.loads((ROOT / 'build/extracted/current.json').read_text())['designs']
    physical_active = json.loads((ROOT / 'build/layout/current.json').read_text())['designs']
    proofs.update(files([ROOT / 'build/layout/current.json'] +
        [ROOT / physical_active[n]['gds'] for n in ['lvds_bias', 'openlvds_delay_line']]))
    exact = dict(openlvds_driver_core=driver, openlvds_receiver_core=receiver,
                 openlvds_dll_analog=dll, lvds_pfd=pfd, openlvds_tx_core=ti,
                 openlvds_ddr_rx=ri, **{n: active[n] for n in ['lvds_bias', 'openlvds_delay_line']})
    for name, info in exact.items():
        checked_netlist(info)
        proofs.update(files([ROOT / info['netlist']]))
        if name != 'lvds_pfd':
            match_model(lib, name, info)
    for name in ['openlvds_dll_analog', 'lvds_pfd', 'lvds_bias']:
        if exact[name]['netlist_sha256'] != dll_models['inputs'][name]:
            raise ValueError('DLL physical metadata differs from qualified inputs')
    proofs.update(files([assembly / 'summary.json', ROOT / 'build/extracted/current.json',
        ROOT / dll_models['layout'] / 'extraction.json', ROOT / dll_models['pfd'] / 'extraction.json']))
    code.update({n: sha(ROOT / 'scripts' / n) for n in CODE})
    selection = dict(exact_models=exact, digital_models={n: exact[n] for n in DIGITAL},
        inputs={n: exact[n]['netlist_sha256'] for n in BLOCKS},
        scopes={n: closure_hash(lib, n) for n in BLOCKS | {'openlvds_dll'}},
        driver_nodesets=driver_nodesets(lib, a['observations']), compatibility=compat,
        dll_verification=dll_proof, proofs=proofs, code=code)
    return lib, selection


def validate_selection(selection, lib):
    if (set(selection['exact_models']) != BLOCKS or set(selection['inputs']) != BLOCKS or
            set(selection['digital_models']) != DIGITAL or
            set(selection['scopes']) != BLOCKS | {'openlvds_dll'}):
        raise ValueError('Incomplete compensated PHY block selection')
    proof = selection['dll_verification']
    if (proof.get('passed') is not True or len(proof.get('case_reports', {})) != 336 or
            len(proof.get('comparisons', [])) != 10 or
            any(c.get('passed') is not True for c in proof['comparisons'])):
        raise ValueError('Compensated PHY lacks complete native DLL verification')
    for name in BLOCKS:
        if selection['inputs'][name] != selection['exact_models'][name]['netlist_sha256']:
            raise ValueError('Selected physical model hash changed')
    if any(selection['digital_models'][n] != selection['exact_models'][n] for n in DIGITAL):
        raise ValueError('Selected digital metadata changed')
    if any(closure_hash(lib, n) != h for n, h in selection['scopes'].items()):
        raise ValueError('Selected circuit closure changed')
    deck = '\n'.join(inst + ' D P N VR PB NB VA VD 0 openlvds_driver_core' for inst in ['XDT', 'XCT'])
    if len(selection['driver_nodesets']) != 8:
        raise ValueError('Require four physical driver-node guesses per core')
    ProbeNetwork(lib).validate(deck, selection['driver_nodesets'])


def prepare(restoration, qualification, tx, rx):
    paths = dict(restoration=restoration.resolve(), qualification=qualification.resolve(),
                 tx=tx.resolve(), rx=rx.resolve())
    if any(not p.is_relative_to(ROOT / 'build/diagnostics') for p in paths.values()):
        raise ValueError('Use isolated physical/scientific candidates')
    lib, selection = assemble(**paths)
    validate_selection(selection, lib)
    if (any(sha(ROOT / n) != h for n, h in selection['proofs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h for n, h in selection['code'].items())):
        raise ValueError('Compensated PHY evidence changed during preparation')
    identity = dict(schema=1, paths={n: str(p.relative_to(ROOT)) for n, p in paths.items()},
        selection=selection, simulator=provenance(), requirements_sha256=sha(ROOT / 'requirements.json'),
        library_sha256=hashlib.sha256(lib.encode()).hexdigest(), scope=
        'Exact physical library after complete compensated driver PVT/long components, '
        'restored short/payload diagnostic, admitted preferred receiver and all 336 native DLL '
        'cases. Explicit restored TX/native capture. Diagnostic only: DLL stability/recovery/'
        'readiness/OTA, measured phase replay, >=256 training cycles, long payloads, aperture '
        'margin, all link conditions, joint RC certificates and PHY release remain separate gates.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = out / 'full.spice'
        if path.exists() and path.read_text() != lib:
            raise ValueError('Prepared compensated PHY changed')
        if not path.exists():
            path.write_text(lib)
        capture_manifest(out / 'manifest.json', dict(identity=identity, **FLAGS))
    return out


def load(bundle, fast=False):
    if fast:
        raise ValueError('Compensated PHY staging is exact-RC only')
    out = Path(bundle).resolve()
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Use an explicit compensated PHY bundle')
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (i.get('schema') != 1 or any(m.get(n) is not v for n, v in FLAGS.items()) or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
            i['simulator'] != provenance() or i['requirements_sha256'] != sha(ROOT / 'requirements.json')):
        raise ValueError('Compensated PHY identity or diagnostic scope changed')
    s = i['selection']
    paths = {n: (ROOT / p).resolve() for n, p in i['paths'].items()}
    if (set(paths) != {'restoration', 'qualification', 'tx', 'rx'} or
            any(not p.is_relative_to(ROOT / 'build/diagnostics') for p in paths.values()) or
            not paths['restoration'].is_relative_to(ROOT / 'build/diagnostics' / restored.NAMESPACE) or
            not paths['qualification'].is_relative_to(ROOT / 'build/diagnostics/dll_qualification')):
        raise ValueError('Compensated PHY parent selection changed')
    if not set(CODE) <= set(s['code']) or not s['proofs']:
        raise ValueError('Compensated PHY provenance is incomplete')
    for name, h in s['proofs'].items():
        p = (ROOT / name).resolve()
        if not p.is_relative_to(ROOT) or sha(p) != h:
            raise ValueError('Compensated PHY scientific/physical evidence changed')
    if any(sha(ROOT / 'scripts' / n) != h for n, h in s['code'].items()):
        raise ValueError('Compensated PHY producer changed')
    lib = (out / 'full.spice').read_bytes()
    if hashlib.sha256(lib).hexdigest() != i['library_sha256']:
        raise ValueError('Compensated PHY library changed')
    validate_selection(s, lib.decode())
    for name, info in s['exact_models'].items():
        checked_netlist(info)
        if name != 'lvds_pfd':
            match_model(lib.decode(), name, info)
    return lib, s['inputs'], s['digital_models']


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'check']); p.add_argument('artifact', type=Path)
    p.add_argument('--qualification', type=Path); p.add_argument('--tx', type=Path); p.add_argument('--rx', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        if any(v is None for v in [a.qualification, a.tx, a.rx]):
            p.error('--qualification, --tx and --rx required')
        with redirect_stdout(sys.stderr):
            out = prepare(a.artifact, a.qualification, a.tx, a.rx)
        print(out, flush=True)
    else:
        data, inputs, _ = load(a.artifact)
        print(json.dumps(dict(verified=True, qualified=False, library_sha256=hashlib.sha256(data).hexdigest(),
                              inputs=inputs), indent=2), flush=True)
