#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Follow one exact regular-pair pilot into gated native routing, GDS and RC."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import run_unguarded_bank_chain_v177 as chain
import math
from run_strong_storage_counter_followup_v235 import owner_mode

ROOT=chain.ROOT
ROUTE='regular_regenerated_bank_route_v278'
NATIVE='regular_regenerated_native_gds_v282'
RC='regular_regenerated_joint_rc_v283'
NATIVE_FLAGS=('all_input_output_pulses_present','input_timing_stimulus_passed','full_swing_pulses_passed',
              'unwrapped_native_epoch_passed','pulse_order_and_widths_passed','period_screen_passed',
              'repeated_delay_screen_passed','zero_code_quarter_passed','terminal_screen_passed',
              'control_settling_passed','current_downstream_250ps_slew_domain_passed',
              'periodic_transport_screen_passed','current_clock_interface_screen_passed')


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
            and physical.get('lvs_passed') is True and params.get('native_mos')==1529 and params.get('native_mims')==43
            and params.get('native_parameters_preserved') is True and bool(r.get('final_mask_proof')) and bool(r.get('final_native_hierarchy_proof')))
    elif stage=='rc':
        params=r.get('native_parameters') or {};fine=r.get('all_fine_junctions') or {};passivity=r.get('passivity') or {}
        ok=(r.get('joint_rc_passed') is True and r.get('regular_regenerated_bank_joint_rc_qualified') is True
            and params.get('native_mos')==1529 and params.get('native_mims')==43 and params.get('native_primitives')==1572
            and params.get('newly_characterized_junction_devices')==0 and params.get('native_parameters_preserved') is True
            and r.get('native_topology_verified') is True and r.get('original_extraction_preserved') is True
            and r.get('original_and_corrected_reductions_regenerated') is True
            and all((fine.get(k) or {}).get('fine_mos_with_all_measured_junction_fields')==155 for k in ('reference','joint_rc'))
            and set(passivity)=={'original_raw','corrected_raw','corrected_reduced'}
            and all(p.get('elementwise_passive_passed') is True for p in passivity.values())
            and (r.get('independent_terminal_current_witness') or {}).get('passed') is True)
    else:raise ValueError('Unknown regular-pair physical stage')
    if not ok:raise ValueError('Native physical stage gate failed; retain artifact')
    return r


def require_pilot(source):
    if json.loads((source/'state.json').read_text())!=dict(status='complete',cases=4,errors=0,qualified_phy=False):
        raise ValueError('Require exact complete four-point regular-pair pilot')
    m=json.loads((source/'manifest.json').read_text());i=m['identity'];r=json.loads((source/'summary.json').read_text());rows=r.get('rows') or []
    if (i['version']!='qualified-regular-p20n16-pair-output-regeneration-native-pilot-v263.1'
        or len(rows)!=4 or [row['task'] for row in rows]!=m['tasks']
        or [row['spec'] for row in rows]!=i['specs'] or len(i['observations']['devices'])!=1529
        or len(i['observations']['programming_gates'])!=173):raise ValueError('Require exact complete four-point regular-pair pilot')
    if [(s['coarse'],s['fine'],s['duty']) for s in i['specs']]!=[(0,0,.5),(0,31,.6),(0,31,.4),(1,0,.5)]:
        raise ValueError('Native regular-pair pilot coverage changed')
    for row in rows:
        v=row.get('result') or {}
        if (row.get('error') is not None or not all(v.get(k) is True for k in NATIVE_FLAGS)
            or len(v.get('terminal_stress',[]))!=1529 or any(d.get('passed') is not True for d in v['terminal_stress'])
            or len(v.get('programming_gates',[]))!=173 or any(d.get('passed') is not True for d in v['programming_gates'])
            or len(v.get('controls',[]))!=len(i['observations']['controls']) or any(d.get('passed') is not True for d in v['controls'])
            or any(len(v.get('edge_delays_ps',{}).get(edge,[]))!=8 or any(not math.isfinite(x) or x<=0 for x in v['edge_delays_ps'][edge]) for edge in ('rise','fall'))):
            raise ValueError('Regular-pair native point or complete safety/control/history coverage failed')
    by={(r['spec']['coarse'],r['spec']['fine'],r['spec']['duty']):r['result'] for r in rows}
    overlap={edge:min(v for d in (.4,.6) for v in by[0,31,d]['edge_delays_ps'][edge])-max(by[1,0,.5]['edge_delays_ps'][edge]) for edge in ('rise','fall')}
    c=r.get('comparison') or {}
    if (c.get('component_hypothesis_passed') is not True or c.get('complete_four_point_native_screen') is not True
        or c.get('conservative_coarse_overlap_ps')!=overlap or not all(v>0 for v in overlap.values())):
        raise ValueError('Regular-pair conservative zero/overlap/duty gate did not pass')
    return r


def require_inputs(source,evidence,junctions,reference):
    folders=[(source,'regular_regenerated_bank_v263'),(evidence,'regular_regenerated_routing_verification_v275'),
             (junctions,'regular_regenerated_junctions_v276'),(reference,'regular_regenerated_junction_reference_v279')]
    for folder,context in folders:
        identity=json.loads((folder/'manifest.json').read_text())['identity']
        if (folder.parent!=ROOT/'build/diagnostics'/context
            or folder.name!=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]):
            raise ValueError('Require explicit unchanged regular-pair native/physical handoffs')
    ei=json.loads((evidence/'manifest.json').read_text())['identity']
    ii=json.loads((ROOT/ei['parent']/'manifest.json').read_text())['identity']
    gi=json.loads((junctions/'manifest.json').read_text())['identity']
    pi=json.loads((ROOT/gi['parent']/'manifest.json').read_text())['identity']
    if ii['parent']!=gi['parent'] or pi['pilot_library']!=str((source/'bank.spice').relative_to(ROOT)):
        raise ValueError('Native pilot and interface/junctions belong to different placements')
    files=[]
    for folder in (evidence,junctions,reference):
        report=json.loads((folder/'summary.json').read_text());state=json.loads((folder/'state.json').read_text())
        expected=dict(status='complete',analysis_completed=True,qualified_phy=False) if folder==junctions else dict(status='complete',passed=True,qualified_phy=False)
        if state!=expected:raise ValueError('Regular-pair physical prerequisite incomplete or failed')
        files += [folder/n for n in ('manifest.json','summary.json','state.json',*report['files'])]
    er=json.loads((evidence/'summary.json').read_text());gr=json.loads((junctions/'summary.json').read_text())
    if (er.get('stored_database_verification_passed') is not True or len(er.get('positive_controls',[]))!=3
        or len(er.get('negative_controls',[]))!=10 or any(r.get('rejected') is not True for r in er['negative_controls'])
        or gr.get('geometry',{}).get('fine_instances')!=31 or gr.get('native_census',{}).get('native_mos')!=1529):
        raise ValueError('Regular-pair native interface or geometry coverage failed')
    return files


def imported_files(module,python):
    code="import sys,json;from pathlib import Path;sys.path.insert(0,'scripts');import "+module+" as p;print(json.dumps(sorted({str(Path(m.__file__).resolve().relative_to(p.ROOT)) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})))"
    p=subprocess.run([str(ROOT/'scripts/env.sh'),'--tools','--ngspice',python,'-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    return [ROOT/n for n in json.loads(p.stdout)]


def run(unit,source,evidence,junctions,reference,out):
    out.mkdir(parents=True,exist_ok=False);info=chain.unit_info(unit);invocation=info.get('InvocationID')
    s=json.loads((source/'state.json').read_text());owner_mode(info,invocation,s.get('status')=='complete')
    files=[Path(__file__),Path(chain.__file__),ROOT/'scripts/run_strong_storage_counter_followup_v235.py',source/'manifest.json',source/'bank.spice',
           *require_inputs(source,evidence,junctions,reference),*imported_files('qualify_regular_regenerated_joint_rc_v283','python3'),
           *imported_files('probe_regular_regenerated_bank_v263','build/tools/exact-rc-venv/bin/python')]
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
                require_pilot(source)
                for name in ('state.json','summary.json'):inputs[str((source/name).relative_to(ROOT))]=sha(source/name)
                break
            time.sleep(10)
        save('preparing_route');printed=execute('route_regular_regenerated_bank_v278.py','prepare',evidence,'route_prepare.log',
            ('--timing',str(source.relative_to(ROOT)),'--junctions',str(junctions.relative_to(ROOT))))
        routed=chain.artifact_from_log(printed,ROUTE)
        if routed is None:raise ValueError('Missing explicit isolated route handoff')
        artifacts['route']=str(routed.relative_to(ROOT));save('routing');execute('route_regular_regenerated_bank_v278.py','run',routed,'route_run.log');require_result(routed,'route')
        save('preparing_native_gds');printed=execute('build_regular_regenerated_native_gds_v282.py','prepare',routed,'native_prepare.log')
        native=chain.artifact_from_log(printed,NATIVE)
        if native is None:raise ValueError('Missing explicit isolated native GDS handoff')
        artifacts['native_gds']=str(native.relative_to(ROOT));save('qualifying_native_gds');execute('build_regular_regenerated_native_gds_v282.py','run',native,'native_run.log');require_result(native,'native')
        save('preparing_joint_rc');printed=execute('qualify_regular_regenerated_joint_rc_v283.py','prepare',native,'rc_prepare.log',('--geometry',str(junctions.relative_to(ROOT))))
        rc=chain.artifact_from_log(printed,RC)
        if rc is None:raise ValueError('Missing explicit regular-pair shared-RC handoff')
        artifacts['joint_rc']=str(rc.relative_to(ROOT));save('qualifying_joint_rc');execute('qualify_regular_regenerated_joint_rc_v283.py','run',rc,'rc_run.log');require_result(rc,'rc')
        save('regular_pair_joint_rc_complete',scope='Gated route, native DRC/LVS/masks and fresh shared RC only; periodic/PVT, full-clock, management warmup and PHY remain unqualified')
    except Exception as e:save('failed',error=str(e));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer-unit',required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--junctions',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.producer_unit,a.source.resolve(),a.evidence.resolve(),a.junctions.resolve(),a.reference.resolve(),a.output.resolve())
