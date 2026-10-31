#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract and independently audit an isolated buffered RX candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from audit_rc import collapse
from digital_candidate_rc import reference_schematic
from extract import extract
from harden_rx_buffer4 import atomic, digest
from lvs_utils import clean_match, strict_setup
from rx_buffered_policy import retained, policy_parameters
from spice_library import checked_netlist

ROOT=Path(__file__).resolve().parents[1]


def captured_inputs(out):
    manifest=json.loads((out/'summary.json').read_text());identity=json.loads((out/'identity.json').read_text())
    parameters=policy_parameters(manifest['rx_policy'])
    if not (manifest['passed'] and manifest['returncode']==0 and manifest['inputs_unchanged'] and
            manifest['interface_verified'] and identity.get('rx_policy',manifest['rx_policy'])==manifest['rx_policy'] and
            manifest['source_sha256']==hashlib.sha256(json.dumps(identity['inputs'],sort_keys=True).encode()).hexdigest()):
        raise ValueError('RX physical candidate has not passed')
    archive=ROOT/manifest['input_archive']
    for name,stamp in identity['inputs'].items():
        if digest(out/'config.json' if name=='config.json' else archive/name)!=stamp:raise ValueError('Captured RX input changed')
    for name,stamp in identity['producer_code'].items():
        if digest(ROOT/'scripts'/name)!=stamp or digest(out/'producers'/name)!=stamp:raise ValueError('RX physical producer changed')
    netlist=ROOT/manifest['run']/'final/nl/openlvds_ddr_rx.nl.v'
    if not retained(netlist.read_text(),**parameters):raise ValueError('RX native output/sampling topology changed')
    return manifest


def run(out):
    out=out.resolve()
    if not out.is_relative_to(ROOT/'build/diagnostics'):raise ValueError('Use an isolated RX physical artifact')
    manifest=captured_inputs(out);folder=ROOT/manifest['run'];gds=folder/'final/gds/openlvds_ddr_rx.gds'
    record=out/'extraction.json';info=json.loads(record.read_text()) if record.exists() else {}
    fingerprint=hashlib.sha256(gds.read_bytes()+(ROOT/'scripts/extract.py').read_bytes()).hexdigest()
    if not (info.get('passed') and info.get('fingerprint')==fingerprint and info.get('source_sha256')==manifest['source_sha256']):
        info=extract('openlvds_ddr_rx',gds,manifest['source_sha256']);atomic(record,info)
    if set(info['ports'])!=set('VGND VPWR clk data[0] data[1] reset_n serial valid'.split()):raise ValueError('RX public terminals changed')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';cells=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    native=checked_netlist(info);physical=folder/'final/spice/openlvds_ddr_rx.spice';audit=out/'rc_audit';audit.mkdir(exist_ok=True)
    collapsed=audit/'wire_collapsed.spice';collapsed.write_text(collapse(native))
    reference=audit/'reference.spice';reference.write_text(reference_schematic(physical.read_text(),cells.read_text()))
    setup=strict_setup(audit/'setup.tcl',pdk/'libs.tech/netgen/sky130A_setup.tcl');report=audit/'lvs.log'
    result=subprocess.run(['netgen','-batch','lvs',f'{collapsed} openlvds_ddr_rx',f'{reference} openlvds_ddr_rx',str(setup),str(report)],cwd=audit,capture_output=True,text=True)
    (audit/'console.log').write_text(result.stdout+result.stderr)
    passed=clean_match(report.read_text() if report.exists() else '',result.returncode)
    captured_inputs(out)
    summary=dict(passed=passed,qualified_phy=False,source_sha256=manifest['source_sha256'],gds_sha256=digest(gds),
        netlist_sha256=info['netlist_sha256'],physical_spice_sha256=digest(physical),pdk_cells_sha256=digest(cells),
        reference_sha256=digest(reference),producer_sha256=digest(Path(__file__)),report=str(report.relative_to(ROOT)),
        report_sha256=digest(report) if report.exists() else None)
    atomic(out/'rc_audit.json',summary);print(out/'rc_audit.json',flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('physical',type=Path);a=p.parse_args();raise SystemExit(run(a.physical))
