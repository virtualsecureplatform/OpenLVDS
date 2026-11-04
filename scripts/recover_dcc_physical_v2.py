#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recover a complete clean DCC flow whose strict summary rejected Infinity.

Keep the original producer, run and failed state untouched. Bind the exact GDS
consumed by physical checks, preserve nonfinite timing as explicit diagnostics,
then freshly extract and independently audit topology in a separate receipt.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import harden_dcc_v2 as original
from dcc_recovery_metrics_v2 import physical_clean,explicit_metrics
from dcc_physical_policy_v3 import interface_retained

ROOT=original.ROOT
NAME=original.NAME
sha=original.sha
VERSION='dcc-complete-flow-summary-recovery-v2.1'


def prepare(parent):
    original.bound(parent)
    if (parent/'summary.json').exists():raise ValueError('Recovery requires the retained missing-summary failure')
    run=parent/'runs'/('dcc-v2-'+parent.name[:12]);metrics_path=run/'final/metrics.json'
    metrics=json.loads(metrics_path.read_text());flow_log=(parent/'flow.log').read_text()
    if 'Flow complete.' not in flow_log or not physical_clean(metrics):raise ValueError('Require completed clean physical checks')
    gds=run/'final/gds'/f'{NAME}.gds';nl=run/'final/nl'/f'{NAME}.nl.v';spice=run/'final/spice'/f'{NAME}.spice'
    if not interface_retained(nl.read_text()):raise ValueError('Clock-hold topology changed')
    # Signoff step inputs must identify the same exact GDS, not another layout.
    stages=['magic-drc','klayout-drc','magic-spiceextraction','netgen-lvs']
    files=[parent/'manifest.json',parent/'state.json',parent/'config.json',parent/'flow.log',metrics_path,gds,nl,spice]
    for stage in stages:
        folders=list(run.glob('*-'+stage))
        if len(folders)!=1:raise ValueError('Missing or duplicate physical-check stage: '+stage)
        state=folders[0]/'state_in.json';data=json.loads(state.read_text());checked=Path(data['gds'])
        if not checked.is_relative_to(ROOT) or sha(checked)!=sha(gds):raise ValueError('Signoff used different GDS bytes')
        files.extend([state,checked])
    code=[Path(__file__),ROOT/'scripts/dcc_recovery_metrics_v2.py',ROOT/'scripts/dcc_physical_policy_v3.py',Path(original.__file__),
        ROOT/'scripts/extract.py',ROOT/'scripts/audit_rc.py',ROOT/'scripts/reduce_rc.py',ROOT/'scripts/digital_candidate_rc.py',
        ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),run=str(run.relative_to(ROOT)),
        files={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code},tools=original.tool_identity())
    out=ROOT/'build/diagnostics/dcc_physical_recovery_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);original.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/dcc_physical_recovery_v2') or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=v for n,v in {**i['files'],**i['code']}.items()) or original.tool_identity()!=i['tools']):
        raise ValueError('Recovery source or physical witnesses changed')
    original.bound(ROOT/i['parent']);return m


def run(out):
    m=bound(out);folder=ROOT/m['identity']['run']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior recovery execution')
        original.atomic(out/'state.json',dict(status='extracting_native_rc',qualified_phy=False))
        metrics=json.loads((folder/'final/metrics.json').read_text());normalized,nonfinite=explicit_metrics(metrics)
        physical=folder/'final/spice'/f'{NAME}.spice'
        pdk=Path(original.os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
        reference=original.reference_schematic(physical.read_text(),pdk.read_text())
        scope=hashlib.sha256(reference.encode()).hexdigest()
        info=original.extract(NAME,folder/'final/gds'/f'{NAME}.gds',sha(out/'manifest.json'),source_scope=scope)
        original.atomic(out/'extraction.json',info)
        summary=dict(run=m['identity']['run'],physical_implementation_passed=True,metrics=normalized,nonfinite_metrics=nonfinite,
            original_producer_returncode_unrecorded=True,flow_completion_marker_present=True,source_sha256=sha(out/'manifest.json'),
            interface_verified=True,original_exact_tie_name_validator_passed=original.interface_retained((folder/'final/nl'/f'{NAME}.nl.v').read_text()),
            constant_tie_clones_validated=True,power_only_decap_endcaps_validated=True,
            qualified_phy=False,electrical_qualification_passed=False,sta_timing_qualified=False)
        audit=original.rc_audit(out,summary,info) if info['passed'] else dict(passed=False)
        if info['passed'] and audit.get('reference_sha256')!=scope:raise ValueError('Recovered schematic scope hash differs')
        bound(out);summary.update(native_rc_extracted=info['passed'],rc_topology_verified=audit['passed'],
            scope='Separate physical/RC recovery only; original failure retained; native RC clock timing and whole PHY remain unqualified')
        original.atomic(out/'summary.json',summary)
        original.atomic(out/'state.json',dict(status='physical_rc_complete' if info['passed'] and audit['passed'] else 'held_rc_failed',qualified_phy=False))
        return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2,allow_nan=False),flush=True)
