#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture an isolated PHY library from audited DLL and serializer candidates."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from digital_candidate_rc import captured_inputs
from dll_campaign import atomic, closure
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


def assemble(qualification,tx,fast=False):
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
    if set(extracted['ports'])!=set(models['openlvds_tx_core']['ports']):
        raise ValueError('TX candidate changes the public terminal set')
    dll=(qualification/('fast.spice' if fast else 'full.spice')).read_text()
    text=overlay(base.decode(),dll,'openlvds_dll',UNCHANGED)
    text=overlay(text,checked_netlist(extracted),'openlvds_tx_core',UNCHANGED+('openlvds_dll',))
    fields=manifest['identity']['fast_models' if fast else 'full_models']
    inputs.update(fields['inputs']);inputs['openlvds_tx_core']=extracted['netlist_sha256']
    models['openlvds_tx_core']=extracted
    reports={str(p.relative_to(ROOT)):digest(p) for p in [tx/'summary.json',tx/'extraction.json',tx/'rc_audit.json',netlist]}
    reports.update(fields['physical_reports'])
    return text,dict(inputs=inputs,digital_models=models,physical_reports=reports,
        exact_tx_sha256=exact_tx,observation_nodes=fields['observation_nodes'],
        scopes={name:closure_hash(text,name) for name in UNCHANGED+('openlvds_dll','openlvds_tx_core')})


def prepare(qualification,tx):
    qualification=qualification.resolve();tx=tx.resolve()
    if not all(p.is_relative_to(ROOT/'build/diagnostics') for p in [qualification,tx]):
        raise ValueError('Use isolated candidate artifacts under build/diagnostics')
    full,full_info=assemble(qualification,tx)
    fast,fast_info=assemble(qualification,tx,True)
    identity=dict(qualification=str(qualification.relative_to(ROOT)),tx=str(tx.relative_to(ROOT)),
        qualification_manifest_sha256=digest(qualification/'manifest.json'),
        requirements_sha256=digest(ROOT/'requirements.json'),
        producer_sha256=digest(Path(__file__)),full=full_info,fast=fast_info,
        full_sha256=hashlib.sha256(full.encode()).hexdigest(),fast_sha256=hashlib.sha256(fast.encode()).hexdigest())
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
    a=parser.parse_args();prepare(a.qualification,a.tx)


if __name__=='__main__':main()
