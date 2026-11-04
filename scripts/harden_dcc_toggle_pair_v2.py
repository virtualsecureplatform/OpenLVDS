#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Physical diagnostic for reset-qualified toggles, never production admission.

Source pilots expose internal excursions whose dependence on actual native
interconnect needs an extracted experiment. No passing source, STA or electrical
qualification is implied by allowing this explicitly unqualified diagnostic.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import harden_dcc_v2 as original
from dcc_recovery_metrics_v2 import physical_clean,explicit_metrics
from dcc_toggle_pair_physical_policy_v2 import interface_retained
from spice_library import checked_netlist

ROOT=original.ROOT
NAME='openlvds_dcc_toggle_pair_v2'
VERSION='reset-qualified-toggle-pair-physical-diagnostic-v2.1'
sha=original.sha
atomic=original.atomic


def source_binding(parent):
    env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','PYTHONHOME']}
    result=subprocess.run(['/usr/bin/python3',str(ROOT/'scripts/probe_dcc_toggle_pair_v3.py'),'bound',str(parent)],
        cwd=ROOT,env=env,capture_output=True,text=True)
    if result.returncode:raise ValueError('Source diagnostic context changed: '+result.stderr[-1000:])
    m=json.loads(result.stdout)
    if m['identity']['version']!='reset-qualified-feedback-two-toggle-dcc-source-pilot-v2.2':raise ValueError('Wrong source experiment')
    return m


def configuration():
    config=original.configuration();config.update(DESIGN_NAME=NAME,
        VERILOG_FILES=[str(ROOT/'sky130/v2'/f'{NAME}.v')],
        EXTRA_VERILOG_MODELS=[str(ROOT/'sky130/v2/dcc_toggle_pair_blackboxes_v2.v')])
    return config


def prepare(parent):
    source_binding(parent);config=configuration()
    paths=[Path(__file__),ROOT/'scripts/dcc_toggle_pair_physical_policy_v2.py',ROOT/'scripts/dcc_recovery_metrics_v2.py',
        Path(original.__file__),ROOT/'sky130/v2'/f'{NAME}.v',ROOT/'sky130/v2/dcc_toggle_pair_blackboxes_v2.v',
        ROOT/'constraints/v2/dcc.sdc',ROOT/'constraints/v2/dcc_pins.cfg',ROOT/'scripts/probe_dcc_toggle_pair_v3.py',
        ROOT/'scripts/extract.py',ROOT/'scripts/reduce_rc.py',ROOT/'scripts/digital_candidate_rc.py',ROOT/'scripts/audit_rc.py',
        ROOT/'scripts/spice_library.py',ROOT/'scripts/lvs_utils.py',parent/'manifest.json',parent/'gated2.spice']
    if not interface_retained((ROOT/'sky130/v2'/f'{NAME}.v').read_text()):raise ValueError('Candidate RTL topology failed')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    files=[pdk/'libs.ref/sky130_fd_sc_hd'/n for n in ['lef/sky130_fd_sc_hd.lef','gds/sky130_fd_sc_hd.gds',
        'lib/sky130_fd_sc_hd__tt_025C_1v80.lib','spice/sky130_fd_sc_hd.spice']]
    files += [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        pdk_files={str(p):sha(p) for p in files},configuration=config,tools=original.tool_identity())
    out=ROOT/'build/diagnostics/dcc_toggle_pair_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    atomic(out/'config.json',config);return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or i['tools']!=original.tool_identity() or json.loads((out/'config.json').read_text())!=i['configuration']):
        raise ValueError('Toggle physical diagnostic changed')
    source_binding(ROOT/i['parent']);return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain physical diagnostic')
        atomic(out/'state.json',dict(status='hardening',qualified_phy=False));tag='dcc-pair-'+out.name[:12]
        args=['python3','-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],'-p','sky130A',
            '-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar','--run-tag',tag,str(out/'config.json')]
        with (out/'flow.log').open('w') as log:process=subprocess.run(args,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        folder=out/'runs'/tag;metrics_path=folder/'final/metrics.json'
        metrics=json.loads(metrics_path.read_text()) if metrics_path.exists() else {};values,nonfinite=explicit_metrics(metrics)
        nl=folder/'final/nl'/f'{NAME}.nl.v';topology=nl.exists() and interface_retained(nl.read_text())
        gds=folder/'final/gds'/f'{NAME}.gds';signoff_gds=True
        for stage in ['magic-drc','klayout-drc','magic-spiceextraction','netgen-lvs']:
            states=list(folder.glob('*-'+stage+'/state_in.json'))
            if len(states)!=1 or not gds.exists():signoff_gds=False;continue
            checked=Path(json.loads(states[0].read_text())['gds'])
            if not checked.is_relative_to(ROOT) or sha(checked)!=sha(gds):signoff_gds=False
        passed=bool(process.returncode==0 and physical_clean(metrics) and topology and signoff_gds)
        summary=dict(returncode=process.returncode,run=str(folder.relative_to(ROOT)),metrics=values,nonfinite_metrics=nonfinite,
            interface_verified=topology,signoff_same_gds=signoff_gds,physical_implementation_passed=passed,
            qualified_phy=False,sta_qualified=False,electrical_qualification_passed=False)
        atomic(out/'summary.json',summary)
        if passed:
            atomic(out/'state.json',dict(status='extracting_native_rc',qualified_phy=False))
            cells=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
            reference=original.reference_schematic((folder/'final/spice'/f'{NAME}.spice').read_text(),cells.read_text())
            scope=hashlib.sha256(reference.encode()).hexdigest()
            info=original.extract(NAME,gds,sha(out/'manifest.json'),source_scope=scope);atomic(out/'extraction.json',info)
            audit=out/'rc_audit';audit.mkdir();(audit/'reference.spice').write_text(reference)
            match=False
            if info['passed']:
                (audit/'wire_collapsed.spice').write_text(original.collapse(checked_netlist(info)))
                setup=original.strict_setup(audit/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
                report=audit/'lvs.log';result=subprocess.run(['netgen','-batch','lvs',f'{audit/"wire_collapsed.spice"} {NAME}',
                    f'{audit/"reference.spice"} {NAME}',str(setup),str(report)],cwd=audit,capture_output=True,text=True)
                (audit/'console.log').write_text(result.stdout+result.stderr)
                match=original.clean_match(report.read_text() if report.exists() else '',result.returncode)
            summary.update(native_rc_extracted=info['passed'],rc_topology_verified=match,reference_sha256=scope)
            atomic(out/'summary.json',summary)
        bound(out);atomic(out/'state.json',dict(status='physical_rc_complete' if passed and summary.get('rc_topology_verified') else 'held_physical_diagnostic',qualified_phy=False))
        return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
