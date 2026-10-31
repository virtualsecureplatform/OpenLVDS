#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture an isolated PHY library from audited DLL and serializer candidates."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from digital_candidate_rc import captured_inputs
from dll_campaign import atomic, closure, text_block
from dll_candidate_library import audited, approximate
from physical_policy import tx_buffered_paths_retained, delay_cells_absent
from qualify_dll_candidate import validate
from spice_library import checked_netlist, library, replace
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]
UNCHANGED=('openlvds_driver','openlvds_receiver','openlvds_delay_line','openlvds_ddr_rx')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def overlay(base,candidate,top,protected=()):
    """Replace the complete candidate closure and prove unrelated circuits unchanged."""
    before={name:closure_hash(base,name) for name in protected}
    selected=closure(candidate,[top])
    for match in re.finditer(r'(?ims)^\.subckt\s+(\S+)\s.*?^\.ends[^\n]*',selected):
        name=match[1]
        if re.search(r'(?im)^\.subckt\s+'+re.escape(name)+r'\s',base):
            base=replace(base,name,match[0])
        else:base+='\n'+match[0]+'\n'
    if closure_hash(base,top)!=closure_hash(candidate,top):
        raise ValueError('Candidate hierarchy changed during assembly: '+top)
    if any(closure_hash(base,name)!=stamp for name,stamp in before.items()):
        raise ValueError('Candidate changed a protected circuit closure')
    return base


def assemble(qualification,tx,fast=False,rx=None):
    manifest=json.loads((qualification/'manifest.json').read_text())
    validate(qualification,manifest)
    physical=json.loads((tx/'summary.json').read_text())
    if captured_inputs(tx,physical)!='openlvds_tx_core':raise ValueError('Expected a TX candidate')
    netlist=ROOT/physical['run']/'final/nl/openlvds_tx_core.nl.v'
    if not (delay_cells_absent(netlist.read_text()) and tx_buffered_paths_retained(netlist.read_text(),4)):
        raise ValueError('TX candidate lacks the direct buf_4 output topology')
    extracted=json.loads((tx/'extraction.json').read_text())
    gds=ROOT/physical['run']/'final/gds/openlvds_tx_core.gds'
    if extracted['source_sha256']!=physical['source_sha256'] or digest(gds)!=extracted['gds_sha256']:
        raise ValueError('TX candidate extraction is stale')
    audited(tx,extracted)
    exact_tx=extracted['netlist_sha256']
    if fast:extracted=approximate(tx,extracted)
    base,inputs,models=library(extracted=True,digital=True,fast=fast)
    # Native DLL characterization uses the exact shared bias in both views.
    # Normalize the fast baseline before protecting driver/RX closures, so an
    # approximate bias is not silently replaced during the DLL overlay.
    bias,bias_inputs,_=library(extracted=True,designs={'lvds_bias'})
    if closure_hash(bias,'lvds_bias')!=closure_hash((qualification/'full.spice').read_bytes(),'lvds_bias'):
        raise ValueError('Candidate changes the current exact shared bias')
    base=replace(base.decode(),'lvds_bias',text_block(bias.decode(),'lvds_bias')).encode()
    inputs['lvds_bias']=bias_inputs['lvds_bias']
    if set(extracted['ports'])!=set(models['openlvds_tx_core']['ports']):
        raise ValueError('TX candidate changes the public terminal set')
    dll=(qualification/('fast.spice' if fast else 'full.spice')).read_text()
    text=overlay(base.decode(),dll,'openlvds_dll',UNCHANGED)
    text=overlay(text,checked_netlist(extracted),'openlvds_tx_core',UNCHANGED+('openlvds_dll',))
    fields=manifest['identity']['fast_models' if fast else 'full_models']
    pfd_root=ROOT/fields['pfd'];pfd_info=json.loads((pfd_root/'extraction.json').read_text())
    if fast:pfd_info=approximate(pfd_root,pfd_info)
    if pfd_info['netlist_sha256']!=fields['inputs']['lvds_pfd']:
        raise ValueError('Staged PFD metadata differs from the native library')
    models['lvds_pfd']=pfd_info
    inputs.update(fields['inputs']);inputs['openlvds_tx_core']=extracted['netlist_sha256']
    models['openlvds_tx_core']=extracted
    reports={str(p.relative_to(ROOT)):digest(p) for p in [tx/'summary.json',tx/'extraction.json',tx/'rc_audit.json',netlist]}
    reports.update(fields['physical_reports'])
    exact_rx=None
    if rx is not None:
        from rx_candidate_aperture import audited_model
        rx_info,rx_reports=audited_model(rx)
        exact_rx=rx_info['netlist_sha256']
        if fast:rx_info=approximate(rx,rx_info)
        if set(rx_info['ports'])!=set(models['openlvds_ddr_rx']['ports']):
            raise ValueError('RX candidate changes the public terminal set')
        protected=tuple(n for n in UNCHANGED if n!='openlvds_ddr_rx')+('openlvds_dll','openlvds_tx_core')
        text=overlay(text,checked_netlist(rx_info),'openlvds_ddr_rx',protected)
        inputs['openlvds_ddr_rx']=rx_info['netlist_sha256'];models['openlvds_ddr_rx']=rx_info
        reports.update(rx_reports)
    return text,dict(inputs=inputs,digital_models=models,physical_reports=reports,
        exact_tx_sha256=exact_tx,exact_rx_sha256=exact_rx,observation_nodes=fields['observation_nodes'],
        scopes={name:closure_hash(text,name) for name in UNCHANGED+('openlvds_dll','openlvds_tx_core')})


def prepare(qualification,tx,rx=None):
    qualification=qualification.resolve();tx=tx.resolve()
    if not all(p.is_relative_to(ROOT/'build/diagnostics') for p in [qualification,tx]):
        raise ValueError('Use isolated candidate artifacts under build/diagnostics')
    if rx is not None:rx=rx.resolve()
    full,full_info=assemble(qualification,tx,rx=rx)
    fast,fast_info=assemble(qualification,tx,True,rx)
    identity=dict(qualification=str(qualification.relative_to(ROOT)),tx=str(tx.relative_to(ROOT)),
        qualification_manifest_sha256=digest(qualification/'manifest.json'),
        requirements_sha256=digest(ROOT/'requirements.json'),
        producer_sha256=digest(Path(__file__)),full=full_info,fast=fast_info,
        full_sha256=hashlib.sha256(full.encode()).hexdigest(),fast_sha256=hashlib.sha256(fast.encode()).hexdigest())
    if rx is not None:
        from rx_candidate_aperture import extra_code
        identity.update(rx=str(rx.relative_to(ROOT)),rx_producer_code=extra_code())
    root=ROOT/'build/diagnostics/phy_candidate'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    # A staged library carries no electrical release or fast-RC certificate.
    for name,text in [('full.spice',full),('fast.spice',fast)]:
        target=root/name
        if target.exists() and target.read_text()!=text:raise ValueError('Staged candidate changed')
        target.write_text(text)
    atomic(root/'manifest.json',dict(identity=identity,qualified=False,complete_phy_suite=False,
        approximate_transient_qualified=False,diagnostic=True))
    print(root,flush=True)
    return root


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('qualification',type=Path)
    parser.add_argument('--tx',type=Path,default=ROOT/'build/diagnostics/tx_buffer4_physical')
    parser.add_argument('--rx',type=Path,help='Audited isolated RX candidate; active RX remains the default')
    a=parser.parse_args();prepare(a.qualification,a.tx,a.rx)


if __name__=='__main__':main()
