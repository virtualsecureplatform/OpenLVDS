#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh DCC physical implementation, gated by the exact 270-case source proof.

No legacy eight-block/336-case profile or analog DLL loop certificate is used.
DRC/LVS and exact-RC topology are physical proofs only; native RC electrical
qualification and the full PHY release remain separate requirements.
"""
import argparse
import fcntl
import hashlib
import json
import itertools
import os
from pathlib import Path
import subprocess

from dcc_physical_policy_v2 import interface_retained
import expand_dcc_clock_hold_v2 as source
import verify_dcc_clock_hold_pvt_v2 as consumer
from digital_candidate_rc import reference_schematic
from audit_rc import collapse
from extract import extract
from lvs_utils import clean_match,strict_setup
from spice_library import checked_netlist

ROOT=Path(__file__).resolve().parents[1]
NAME='openlvds_dcc_clock_hold_v2'
VERSION='dcc-clock-hold-physical-v2.1'
sha=source.base.sha
atomic=source.base.atomic


def source_admission(parent):
    m=source.bound(parent)
    identity=dict(artifact=str(parent.relative_to(ROOT)),manifest_sha256=sha(parent/'manifest.json'),
        summary_sha256=sha(parent/'summary.json'),consumer_sha256=sha(Path(consumer.__file__)))
    receipt=ROOT/'build/diagnostics/dcc_clock_hold_pvt_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]/'summary.json'
    report=json.loads(receipt.read_text())
    if (report['artifact']!=identity['artifact'] or report['consumer_sha256']!=identity['consumer_sha256']
        or report['cases']!=270 or report['numerical_errors']!=0 or report['source_only'] is not True
        or report['qualified_phy'] is not False or len(report['candidates'])!=1):
        raise ValueError('Incomplete independent DCC source proof')
    candidate=report['candidates'][0]
    if (candidate['topology']!=[1,'clock_hold','inv_4'] or candidate['cases']!=270 or candidate['pvt_count']!=15
        or candidate['source_screen_passed'] is not True):raise ValueError('DCC candidate failed source qualification')
    rows=json.loads((parent/'summary.json').read_text())['rows']
    if len(m['tasks'])!=270 or [r['task'] for r in rows]!=m['tasks']:
        raise ValueError('DCC source case coverage changed')
    expected=set(itertools.product(['tt','ff','ss','fs','sf'],[0,25,40],[390,400,410],[20,250],[0,-140,140]))
    actual=set()
    required={str((parent/n).relative_to(ROOT)) for n in ['manifest.json','summary.json','state.json']}
    for row in rows:
        spec=row['task']['spec'];actual.add(tuple(spec[k] for k in ['process','temperature','mhz','slew_ps','phase_error_ps']))
        if (spec['drive']!=1 or spec['buffers']!=0 or spec['output_cell']!='inv_4'
            or spec['reset_drive']!=1 or row['error'] is not None or not row['result']['event_integrity_passed']
            or not row['result']['pulse_generator_integrity_passed']
            or (spec['phase_error_ps']==0 and row['result']['symmetric_timing_passed'] is not True)):
            raise ValueError('DCC source result no longer passes')
        required.update(str((parent/row['task']['id']/n).relative_to(ROOT)) for n in consumer.reader.REQUIRED|{'summary.json'})
    if actual!=expected or not required<=set(report['witness_files']):
        raise ValueError('Incomplete DCC source witness coverage')
    if any(sha(ROOT/n)!=v for n,v in report['witness_files'].items()):
        raise ValueError('DCC source witnesses changed')
    return receipt


def configuration():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    tt=str(pdk/'libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib')
    return dict(DESIGN_NAME=NAME,VERILOG_FILES=[str(ROOT/'sky130/v2'/f'{NAME}.v')],
        VERILOG_DEFINES=['USE_POWER_PINS'],EXTRA_VERILOG_MODELS=[str(ROOT/'sky130/v2/dcc_blackboxes_v2.v')],
        CLOCK_PORT=None,CLOCK_PERIOD=2.439024,PNR_SDC_FILE=str(ROOT/'constraints/v2/dcc.sdc'),
        SIGNOFF_SDC_FILE=str(ROOT/'constraints/v2/dcc.sdc'),FP_PIN_ORDER_CFG=str(ROOT/'constraints/v2/dcc_pins.cfg'),
        FP_SIZING='absolute',DIE_AREA=[0,0,60,60],FP_CORE_UTIL=20,PL_TARGET_DENSITY_PCT=35,
        VDD_NETS=['VPWR'],GND_NETS=['VGND'],PAD_LIBS=None,DECAP_CELLS=[],
        LIB={'nom_':[tt],'*_tt_025C_1v80':[tt]},STA_CORNERS=['nom_tt_025C_1v80','min_tt_025C_1v80','max_tt_025C_1v80'],
        EXTRA_EXCLUDED_CELLS=['sky130_fd_sc_hd__clkdlybuf*'],SYNTH_ELABORATE_ONLY=True,SYNTH_HIERARCHY_MODE='flatten',
        RUN_CTS=False,RUN_POST_CTS_RESIZER_TIMING=False,DESIGN_REPAIR_BUFFER_INPUT_PORTS=False,
        DESIGN_REPAIR_BUFFER_OUTPUT_PORTS=False,RUN_POST_GRT_DESIGN_REPAIR=False,RUN_POST_GRT_RESIZER_TIMING=False,
        RUN_MCSTA=False,RUN_EQY=False,LINTER_DISABLE_WARNINGS_BLACKBOX=['UNDRIVEN','UNUSEDSIGNAL','PINMISSING','TIMESCALEMOD'],
        meta=dict(flow='Classic'))


def prepare(parent):
    receipt=source_admission(parent);config=configuration()
    paths=[Path(__file__),ROOT/'scripts/dcc_physical_policy_v2.py',ROOT/'sky130/v2'/f'{NAME}.v',
        ROOT/'sky130/v2/dcc_blackboxes_v2.v',ROOT/'constraints/v2/dcc.sdc',ROOT/'constraints/v2/dcc_pins.cfg',
        ROOT/'scripts/extract.py',ROOT/'scripts/digital_candidate_rc.py',ROOT/'scripts/audit_rc.py',
        ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',
        ROOT/'build/apptainer/openlvds.sif.sha256',Path(consumer.__file__),receipt]
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    pdk_paths=[pdk/'libs.ref/sky130_fd_sc_hd'/suffix for suffix in [
        'lef/sky130_fd_sc_hd.lef','gds/sky130_fd_sc_hd.gds',
        'lib/sky130_fd_sc_hd__tt_025C_1v80.lib','spice/sky130_fd_sc_hd.spice']]
    pdk_paths += [pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    identity=dict(version=VERSION,source=str(parent.relative_to(ROOT)),source_receipt=str(receipt.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files={str(p):sha(p) for p in pdk_paths},configuration=config)
    out=ROOT/'build/diagnostics/dcc_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'inputs').mkdir()
    for n,v in identity['inputs'].items():
        path=out/'inputs'/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/n).read_bytes())
    atomic(out/'config.json',config);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcc_physical_v2'):raise ValueError('Wrong DCC physical context')
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or i['version']!=VERSION
        or any(sha(ROOT/n)!=v or sha(out/'inputs'/n)!=v for n,v in i['inputs'].items())
        or any(sha(Path(n))!=v for n,v in i['pdk_files'].items())
        or json.loads((out/'config.json').read_text())!=i['configuration']):raise ValueError('DCC physical inputs changed')
    return m


def rc_audit(out,manifest,info):
    run=ROOT/manifest['run'];pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    cells=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    physical=run/'final/spice'/f'{NAME}.spice';audit=out/'rc_audit';audit.mkdir()
    collapsed=audit/'wire_collapsed.spice';collapsed.write_text(collapse(checked_netlist(info)))
    reference=audit/'reference.spice';reference.write_text(reference_schematic(physical.read_text(),cells.read_text()))
    setup=strict_setup(audit/'setup.tcl',pdk/'libs.tech/netgen/sky130A_setup.tcl');report=audit/'lvs.log'
    result=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {NAME}',f'{reference} {NAME}',str(setup),str(report)],
        cwd=audit,capture_output=True,text=True)
    (audit/'console.log').write_text(result.stdout+result.stderr)
    passed=clean_match(report.read_text() if report.exists() else '',result.returncode)
    value=dict(passed=passed,netlist_sha256=info['netlist_sha256'],pdk_cells_sha256=sha(cells),
        reference_sha256=sha(reference),physical_spice_sha256=sha(physical),report_sha256=sha(report) if report.exists() else None)
    atomic(out/'rc_audit.json',value);return value


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior physical execution')
        atomic(out/'state.json',dict(status='hardening',qualified_phy=False))
        tag='dcc-v2-'+out.name[:12]
        command=['python3','-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],'-p','sky130A',
            '-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar','--run-tag',tag,str(out/'config.json')]
        with (out/'flow.log').open('w') as log:result=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        bound(out);folder=out/'runs'/tag;metrics_path=folder/'final/metrics.json'
        metrics=json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
        nl=folder/'final/nl'/f'{NAME}.nl.v'
        retained=interface_retained(nl.read_text()) if nl.exists() else False
        keys=['route__drc_errors','magic__drc_error__count','klayout__drc_error__count','design__lvs_error__count',
              'antenna__violating__nets','antenna__violating__pins']
        clean=all(k in metrics and metrics[k]==0 for k in keys)
        summary=dict(returncode=result.returncode,run=str(folder.relative_to(ROOT)),metrics=metrics,
            source_sha256=sha(out/'manifest.json'),interface_verified=retained,physical_implementation_passed=bool(result.returncode==0 and clean and retained),
            qualified_phy=False,electrical_qualification_passed=False)
        atomic(out/'summary.json',summary)
        if not summary['physical_implementation_passed']:
            atomic(out/'state.json',dict(status='held_physical_failed',qualified_phy=False));return summary
        atomic(out/'state.json',dict(status='extracting_native_rc',qualified_phy=False))
        info=extract(NAME,folder/'final/gds'/f'{NAME}.gds',summary['source_sha256']);atomic(out/'extraction.json',info)
        audit=rc_audit(out,summary,info) if info['passed'] else dict(passed=False)
        bound(out);summary.update(native_rc_extracted=info['passed'],rc_topology_verified=audit['passed'])
        atomic(out/'summary.json',summary)
        atomic(out/'state.json',dict(status='physical_rc_complete' if info['passed'] and audit['passed'] else 'held_rc_failed',qualified_phy=False))
        return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args()
    out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(json.dumps(run(out),indent=2),flush=True)
