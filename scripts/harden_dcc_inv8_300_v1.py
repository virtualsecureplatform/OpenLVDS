#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Diagnostic INV8 DCC placement/route/PEX; source stress remains unqualified."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import harden_dcc_v2 as original
from dcc_physical_policy_v3 import interface_retained as legacy_retained
from dcc_recovery_metrics_v2 import explicit_metrics
from digital_candidate_rc import reference_schematic
from extract import extract
from audit_rc import collapse
from spice_library import checked_netlist
from lvs_utils import strict_setup,clean_match

ROOT=original.ROOT
NAME='openlvds_dcc_inv8_300'
CONTEXT='dcc_inv8_physical_300_v1'
sha=original.sha
save=original.atomic
REFERENCE=ROOT/'build/diagnostics/dcc_ng_reference_300_v1/e2f8b3c2c305dc26/26/summary.json'


def retained(text):
    pattern=r'\bsky130_fd_sc_hd__inv_8\s+output_drive\s*\('
    if len(re.findall(pattern,text))!=1:
        return False
    canonical=re.sub(pattern,'sky130_fd_sc_hd__inv_4 output_drive (',text)
    return legacy_retained(canonical)


def configuration():
    c=original.configuration()
    c.update(DESIGN_NAME=NAME,VERILOG_FILES=[str(ROOT/'sky130/v3'/f'{NAME}.v')],
             EXTRA_VERILOG_MODELS=[str(ROOT/'sky130/v3/dcc_inv8_blackboxes_300.v')],
             CLOCK_PERIOD=1000/310,PNR_SDC_FILE=str(ROOT/'constraints/v3/dcc_inv8_300.sdc'),
             SIGNOFF_SDC_FILE=str(ROOT/'constraints/v3/dcc_inv8_300.sdc'),
             FP_PIN_ORDER_CFG=str(ROOT/'constraints/v3/dcc_inv8_300_pins.cfg'))
    return c


def prepare():
    reference=json.loads(REFERENCE.read_text())
    if reference.get('complete') is not True or reference.get('error') is not None or reference['result']['source']['timing_passed'] is not True:
        raise ValueError('Require complete native repaired source timing control')
    c=configuration()
    files=[Path(__file__),REFERENCE,ROOT/'clocking_300mhz.json',ROOT/'scripts/dcc_physical_policy_v3.py',
           ROOT/'scripts/dcc_physical_policy_v2.py',ROOT/'scripts/dcc_recovery_metrics_v2.py',
           ROOT/'scripts/harden_dcc_v2.py',ROOT/'scripts/extract.py',ROOT/'scripts/reduce_rc.py',
           ROOT/'scripts/digital_candidate_rc.py',ROOT/'scripts/audit_rc.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py',
           *map(Path,c['VERILOG_FILES']),*map(Path,c['EXTRA_VERILOG_MODELS']),Path(c['PNR_SDC_FILE']),Path(c['FP_PIN_ORDER_CFG'])]
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    files += [pdk/'libs.ref/sky130_fd_sc_hd'/suffix for suffix in ['lef/sky130_fd_sc_hd.lef','gds/sky130_fd_sc_hd.gds','lib/sky130_fd_sc_hd__tt_025C_1v80.lib','spice/sky130_fd_sc_hd.spice']]
    files += [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    identity=dict(version=CONTEXT,files={str(p):sha(p) for p in files},tools=original.tool_identity(),configuration=c,
                  source_timing_control_complete=True,source_stress_admitted=False,qualified_phy=False,
                  scope='Diagnostic physical candidate only; source stress and full source matrix remain open')
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/diagnostics'/CONTEXT/key
    out.mkdir(parents=True,exist_ok=False)
    save(out/'manifest.json',dict(identity=identity));save(out/'config.json',c)
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or original.tool_identity()!=i['tools']:
        raise ValueError('Physical candidate identity changed')
    if json.loads((out/'config.json').read_text())!=i['configuration']:
        raise ValueError('Candidate configuration changed')
    for p,h in i['files'].items():
        if sha(Path(p))!=h:
            raise ValueError('Candidate input changed: '+p)
    return m


def run(out):
    m=bound(out)
    with (out/'state.json').open('x') as f:json.dump(dict(status='hardening',qualified_phy=False),f)
    tag='dcc-inv8-300-'+out.name[:12]
    command=['python3','-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],'-p','sky130A','-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar','--run-tag',tag,str(out/'config.json')]
    with (out/'flow.log').open('w') as log:p=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT)
    folder=out/'runs'/tag
    metrics_path=folder/'final/metrics.json'
    metrics=json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    normalized,nonfinite=explicit_metrics(metrics)
    nl=folder/'final/nl'/f'{NAME}.nl.v'
    topology=nl.exists() and retained(nl.read_text())
    keys=['route__drc_errors','magic__drc_error__count','klayout__drc_error__count','design__lvs_error__count','antenna__violating__nets','antenna__violating__pins']
    clean=all(k in metrics and metrics[k]==0 for k in keys)
    summary=dict(returncode=p.returncode,run=str(folder.relative_to(ROOT)),metrics=normalized,nonfinite_metrics=nonfinite,
                 interface_verified=bool(topology),physical_checks_passed=bool(p.returncode==0 and clean and topology),
                 sta_timing_qualified=False,source_stress_admitted=False,qualified_phy=False)
    save(out/'summary.json',summary)
    if summary['physical_checks_passed']:
        save(out/'state.json',dict(status='extracting',qualified_phy=False))
        physical=folder/'final/spice'/f'{NAME}.spice'
        pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
        cells=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
        reference=reference_schematic(physical.read_text(),cells.read_text())
        info=extract(NAME,folder/'final/gds'/f'{NAME}.gds',sha(out/'manifest.json'),source_scope=hashlib.sha256(reference.encode()).hexdigest())
        save(out/'extraction.json',info)
        if info['passed']:
            audit=out/'rc_audit';audit.mkdir()
            (audit/'reference.spice').write_text(reference)
            (audit/'collapsed.spice').write_text(collapse(checked_netlist(info)))
            setup=strict_setup(audit/'setup.tcl',pdk/'libs.tech/netgen/sky130A_setup.tcl')
            log=audit/'lvs.log'
            p=subprocess.run(['netgen','-batch','lvs',f'{audit/"collapsed.spice"} {NAME}',f'{audit/"reference.spice"} {NAME}',str(setup),str(log)],cwd=audit,capture_output=True,text=True)
            (audit/'console.log').write_text(p.stdout+p.stderr)
            summary['rc_topology_passed']=clean_match(log.read_text() if log.exists() else '',p.returncode)
        summary['native_rc_extracted']=info['passed']
    bound(out)
    summary['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name in ['extraction.json','lvs.log','reference.spice','collapsed.spice']}
    save(out/'summary.json',summary)
    save(out/'state.json',dict(status='complete' if summary.get('rc_topology_passed') else 'failed',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    elif a.artifact is None:p.error('Supply artifact')
    else:run(a.artifact.resolve())
