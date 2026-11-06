#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow one exact fine-driver pilot into gated routing and native GDS checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import run_discharge_fine_clock_followup_v222 as pilot
from run_strong_storage_counter_followup_v235 import owner_mode

chain=pilot.chain
ROOT=chain.ROOT
ROUTE='isolated_fine_bank_route_v242'
NATIVE='isolated_fine_native_gds_v253'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def require_result(artifact,stage):
    state=json.loads((artifact/'state.json').read_text());r=json.loads((artifact/'summary.json').read_text())
    if state!=dict(status='complete',passed=True,qualified_phy=False):raise ValueError('Native physical stage incomplete or failed')
    if stage=='route':
        ok=r.get('route_bringup_passed') is True and r.get('router_final_violations')==0 and r.get('returncode')==0 and bool(r.get('connection_and_coverage_check'))
    elif stage=='native':
        physical=r.get('physical') or {};params=r.get('native_parameters') or {}
        ok=(r.get('native_routed_gds_passed') is True and physical.get('passed') is True and physical.get('drc_count')=='0'
            and physical.get('lvs_passed') is True and params.get('native_mos')==1479 and params.get('native_mims')==43
            and params.get('native_parameters_preserved') is True and bool(r.get('final_mask_proof')) and bool(r.get('final_native_hierarchy_proof')))
    else:raise ValueError('Unknown isolated physical stage')
    if not ok:raise ValueError('Native physical stage gate failed; retain artifact')
    return r


def cad_imports():
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import build_isolated_fine_native_gds_v253 as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    p=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice','python3','-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    return [ROOT/n for n in json.loads(p.stdout)]


def run(unit,source,evidence,junctions,reference,out):
    out.mkdir(parents=True,exist_ok=False);info=chain.unit_info(unit);invocation=info.get('InvocationID')
    s=json.loads((source/'state.json').read_text());owner_mode(info,invocation,s.get('status')=='complete')
    files=[Path(__file__),Path(pilot.__file__),Path(chain.__file__),ROOT/'scripts/run_strong_storage_counter_followup_v235.py',source/'manifest.json',*cad_imports()]
    for p in (evidence,junctions,reference):
        files += [p/n for n in ('manifest.json','summary.json','state.json')]
    rr=json.loads((reference/'summary.json').read_text());ri=json.loads((reference/'manifest.json').read_text())['identity']
    if (ri['parent']!=str(junctions.relative_to(ROOT)) or json.loads((reference/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or rr.get('ordinary_reference_prepared') is not True or rr.get('all_fine_junctions',{}).get('fine_mos_with_all_measured_junction_fields')!=155):
        raise ValueError('Require explicit complete measured junction-reference handoff')
    files += [reference/n for n in rr['files']]
    inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(files))}
    artifacts=dict(pilot=str(source.relative_to(ROOT)),interface_evidence=str(evidence.relative_to(ROOT)),junctions=str(junctions.relative_to(ROOT)),measured_reference=str(reference.relative_to(ROOT)))
    def save(status,**extra):
        temporary=out/'state.tmp';temporary.write_text(json.dumps(dict(status=status,producer_unit=unit,producer_invocation=invocation,
            inputs=inputs,artifacts=artifacts,qualified_phy=False,**extra),indent=2)+'\n');temporary.replace(out/'state.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured isolated physical continuation input changed')
    def execute(script,action,artifact,logname,extra=()):
        unchanged();command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','python3','scripts/'+script,action,str(artifact.relative_to(ROOT)),*extra]
        with (out/logname).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        unchanged();return (out/logname).read_text()
    save('waiting_for_native_pilot')
    try:
        while True:
            unchanged();s=json.loads((source/'state.json').read_text());mode=owner_mode(chain.unit_info(unit),invocation,s.get('status')=='complete')
            if mode=='complete':
                variants=pilot.require_source(source)
                if dict(driver='p20n16',fine_copies=1) not in variants:raise ValueError('P20/N16 native pilot did not pass; retain physical candidate without routing')
                for name in ('state.json','summary.json'):inputs[str((source/name).relative_to(ROOT))]=sha(source/name)
                break
            time.sleep(10)
        save('preparing_route');printed=execute('route_isolated_fine_bank_v242.py','prepare',evidence,'route_prepare.log',
            ('--timing',str(source.relative_to(ROOT)),'--junctions',str(junctions.relative_to(ROOT))))
        routed=chain.artifact_from_log(printed,ROUTE)
        if routed is None:raise ValueError('Missing explicit isolated route handoff')
        artifacts['route']=str(routed.relative_to(ROOT));save('routing');execute('route_isolated_fine_bank_v242.py','run',routed,'route_run.log');require_result(routed,'route')
        save('preparing_native_gds');printed=execute('build_isolated_fine_native_gds_v253.py','prepare',routed,'native_prepare.log')
        native=chain.artifact_from_log(printed,NATIVE)
        if native is None:raise ValueError('Missing explicit isolated native GDS handoff')
        artifacts['native_gds']=str(native.relative_to(ROOT));save('qualifying_native_gds');execute('build_isolated_fine_native_gds_v253.py','run',native,'native_run.log');require_result(native,'native')
        save('native_physical_complete',scope='Gated route and native DRC/LVS/mask proof only; fresh shared-wire RC, periodic/PVT, full-clock and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--junctions',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.evidence.resolve(),a.junctions.resolve(),a.reference.resolve(),a.output.resolve())
