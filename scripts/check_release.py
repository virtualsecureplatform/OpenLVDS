#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fail closed on missing, stale or failed physical/electrical evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from regression import matrix
from spice_library import library
from rc_certificate import valid as valid_certificate
from lvs_utils import clean_match
from evidence_scope import matches as evidence_matches
from link_evidence import matches as link_matches
from openpll_clock import rtl_sources
from spice_engine import engine,provenance
from phase_evidence import valid as valid_phase_evidence
from physical_policy import delay_cells_absent,pfd_paths_retained,tx_cells_retained

ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path)
    for name in ['stability','recovery','readiness','ota-operating-points']:
        parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    if args.bundle and not all([args.stability,args.recovery,args.readiness,args.ota_operating_points]):
        parser.error('Staged release requires stability, recovery, readiness and OTA operating-point reports')
    bundle=args.bundle.resolve() if args.bundle else None
    if bundle and not bundle.is_relative_to(ROOT/'build/diagnostics/phy_candidate'):
        parser.error('Use an isolated PHY candidate bundle')
    release_out=bundle/'release' if bundle else ROOT/'build/release'
    (release_out/'status.json').unlink(missing_ok=True)
    checks=[];req=json.loads((ROOT/'requirements.json').read_text())
    source=digest(ROOT/'analog/openlvds.spice');requirements=digest(ROOT/'requirements.json')
    simulator_stamp=provenance();analysis_stamp=digest(ROOT/'scripts/verify_analog.py')
    def check(name,condition,detail=''):
        checks.append(dict(name=str(name),passed=bool(condition),detail=detail))
    def read(path):
        p=ROOT/path
        if not p.exists():check(path,False,'Missing evidence');return {}
        try:return json.loads(p.read_text())
        except ValueError:check(path,False,'Invalid JSON');return {}
    staged={};staged_context={};selected_full=None;selected_fast=None;selected_inputs={}
    if bundle:
        try:
            from phy_candidate import load
            from staged_release import gates
            selected_full,selected_inputs,_=load(bundle)
            selected_fast,_,_=load(bundle,True)
            staged=read(bundle/'manifest.json')['identity']
            staged_context=gates(bundle,args.stability,args.recovery,args.readiness,args.ota_operating_points,check)
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            check('staged candidate evidence',False,str(error))
    rtl=read('build/rtl/summary.json')
    check('behavioral coverage',rtl.get('passed') and not rtl.get('smoke',True) and min(rtl.get('rtl_total_bits',0),rtl.get('native_total_bits',0))>=req['minimum_behavioral_bits'] and rtl.get('native_functional_phy_passed',False))
    # Recreate verify_rtl.py's source fingerprint, including its benches/models.
    sources=sorted((ROOT/'rtl').glob('*.v'))+[ROOT/'tb/tb_link.v']
    dll=[ROOT/'rtl/openlvds_dll_control.v',ROOT/'tb/tb_dll_control.v']
    phy=sorted((ROOT/'rtl').glob('*.v'))+[ROOT/'models/analog_functional.v',ROOT/'tb/tb_phy.v']
    stamp=hashlib.sha256(b''.join(p.read_bytes() for p in sources+dll+phy)+(ROOT/'models/sky130_tx_functional.v').read_bytes()+
        (ROOT/'requirements.json').read_bytes()+(ROOT/'scripts/verify_rtl.py').read_bytes()).hexdigest()
    check('behavioral source fingerprint',rtl.get('source_hash')==stamp)
    physical=read('build/layout/current.json')
    physical_source=physical.get('source_sha256')==source
    if bundle:
        from layout import circuits,flatten,schematic_text
        definitions=circuits((ROOT/'analog/openlvds.spice').read_text())
        names=['openlvds_driver_core','openlvds_receiver_core','openlvds_delay_line','lvds_bias']
        physical_source=all(name in physical.get('designs',{}) and
            hashlib.sha256(schematic_text(name,*flatten(definitions,name)).encode()).hexdigest()==
            physical['designs'][name].get('lvs_source_sha256') for name in names)
    check('analog GDS DRC/LVS',physical.get('passed') and physical_source)
    # A generator revision does not invalidate already manufactured geometry;
    # its actual extracted connectivity must pass the current LVS policy.
    for name,info in physical.get('designs',{}).items():
        if bundle and name=='openlvds_dll_analog':continue
        out=(ROOT/info['gds']).parent
        report=out/(name+'.lvs.log')
        check(name+' strict LVS',report.exists() and clean_match(report.read_text()) and
              info.get('lvs_report_sha256')==digest(report))
    for kind in ['tx','rx','pfd']:
        candidate=None
        if bundle and kind=='tx':candidate=ROOT/staged.get('tx','build/physical/missing')
        if bundle and kind=='pfd':
            qualification=read(ROOT/staged.get('qualification','build/physical/missing')/'manifest.json')
            candidate=ROOT/qualification.get('identity',{}).get('full_models',{}).get('pfd','build/physical/missing')
        evidence=read(candidate/'summary.json' if candidate else f'build/physical/{kind}/summary.json')
        check(kind+' digital physical flow',evidence.get('passed'))
        name={'tx':'openlvds_tx_core','rx':'openlvds_ddr_rx','pfd':'lvds_pfd'}[kind]
        netlist=ROOT/evidence.get('run','build/physical/missing')/'final/nl'/f'{name}.nl.v'
        text=netlist.read_text() if netlist.is_file() else ''
        check(kind+' no clock-delay buffers',bool(text) and delay_cells_absent(text))
        if kind=='pfd':
            from pfd_candidate_policy import pfd_candidate_paths_retained
            check('PFD direct clocks and matched drivers',pfd_candidate_paths_retained(text,evidence.get('pfd_policy')) if bundle else pfd_paths_retained(text))
        if kind=='tx':
            from physical_policy import tx_buffered_paths_retained
            check('TX native serializer cells and connections',tx_buffered_paths_retained(text,4) if bundle else tx_cells_retained(text))
        if candidate:
            try:
                from digital_candidate_rc import captured_inputs
                current=captured_inputs(candidate,evidence)==name
            except (OSError,ValueError,KeyError,TypeError):current=False
            check(kind+' archived physical source fingerprint',current)
            continue
        files=[ROOT/'rtl/openlvds_reset.v',ROOT/f'rtl/{name}.v']
        if kind=='tx':files.extend([ROOT/'rtl/openlvds_ddr_tx.v',ROOT/'sky130/tx_blackboxes.v'])
        if kind=='pfd':files=[ROOT/'sky130/lvds_pfd.v',ROOT/'sky130/pfd_blackboxes.v']
        config=ROOT/f'build/physical/{kind}/config.json'
        stamp=hashlib.sha256(b''.join(p.read_bytes() for p in files)+
            (ROOT/f'constraints/{kind}.sdc').read_bytes()+config.read_bytes()).hexdigest() if config.exists() else None
        check(kind+' physical source fingerprint',evidence.get('source_sha256')==stamp and stamp is not None)
    try:
        if bundle:expected_rc,exact=selected_full,selected_inputs
        else:expected_rc,exact,_=library(extracted=True,digital=True)
        if expected_rc is None:raise ValueError('Missing staged library')
        check('distributed RC networks and port bindings',True)
    except (ValueError,KeyError,FileNotFoundError) as error:
        exact={};expected_rc=None;check('distributed RC networks and port bindings',False,str(error))
    try:phase_library,phase_inputs,_=library(extracted=True,designs={'openlvds_dll_analog','lvds_bias'})
    except (ValueError,KeyError,FileNotFoundError):phase_library=None;phase_inputs={}
    for mode in ([] if bundle else ['corners','slew']):
        pointer=read(f'build/phase_detector/current_extracted_{mode}.json')
        check('extracted phase-fault response/'+mode,phase_library is not None and
              valid_phase_evidence(ROOT,pointer,phase_library,phase_inputs,requirements,engine(),simulator_stamp,mode))
    audit=read('build/rc_audit/summary.json')
    for name in ['openlvds_driver_core','openlvds_receiver_core','openlvds_dll_analog','openlvds_delay_line','lvds_bias']:
        if bundle and name=='openlvds_dll_analog':continue
        evidence=audit.get('designs',{}).get(name,{})
        report=ROOT/evidence.get('report','build/rc_audit/missing.log')
        check('RC topology/'+name,evidence.get('passed') and exact.get(name) is not None and
            evidence.get('netlist_sha256')==exact[name] and report.is_file() and
            evidence.get('report_sha256')==digest(report) and clean_match(report.read_text()))
    for root in ['analog','analog_extracted']:
        for test in ['driver','receiver','receiver_rate','dll']:
            if bundle and test=='dll':continue
            scope_test='receiver' if test=='receiver_rate' else test
            for process in req['process_corners']:
                for temp in req['temperatures_c']:
                    folder=ROOT/f'build/{root}/{test}_{process}_{temp}'
                    evidence=read(str(folder.relative_to(ROOT)/'summary.json'))
                    check(f'{root}/{test}/{process}/{temp}',evidence.get('passed') and
                          evidence.get('requirements_sha256')==requirements and
                          evidence.get('simulator')==engine() and evidence.get('simulator_provenance')==simulator_stamp and evidence_matches(evidence,
                            folder/'source.spice',
                            (ROOT/'analog/openlvds.spice').read_bytes() if root=='analog' else expected_rc,scope_test))
                    if test=='driver':
                        check(f'DC output/{root}/{process}/{temp}',evidence.get('dc_output',{}).get('passed') is True)
                    producer=folder/'runner.py';analyzer=folder/'analysis_runner.py'
                    check(f'analysis/{root}/{test}/{process}/{temp}',producer.is_file() and
                        evidence.get('runner_sha256')==digest(producer) and evidence.get('analysis_runner_sha256')==analysis_stamp and
                        (digest(producer)==analysis_stamp or (analyzer.is_file() and digest(analyzer)==analysis_stamp)))
                    for filename,key in [('bench.cir','deck_sha256'),('bench.cir.prn','waveform_sha256')]:
                        path=folder/filename
                        check(f'{filename}/{root}/{test}/{process}/{temp}',path.is_file() and evidence.get(key)==digest(path))
                    if root=='analog_extracted':
                        required={'driver':['lvds_bias','openlvds_driver_core'],
                                  'receiver':['lvds_bias','openlvds_receiver_core'],
                                  'dll':['lvds_bias','openlvds_dll_analog','lvds_pfd']}[scope_test]
                        check(f'RC fingerprint/{test}/{process}/{temp}',all(
                            exact.get(k) is not None and evidence.get('extraction_inputs',{}).get(k)==exact[k]
                            for k in required))
    for clock,trace in [('summary','clock.csv'),('physical_summary','physical_clock.csv')]:
        evidence=read(f'build/openpll/{clock}.json');path=ROOT/'build/openpll'/trace
        check('OpenPLL '+clock,evidence.get('passed') and path.exists() and evidence.get('clock_sha256')==digest(path))
        if clock=='summary':
            stamp=hashlib.sha256(b''.join(p.read_bytes() for p in rtl_sources())).hexdigest()
            check('OpenPLL RTL source fingerprint',evidence.get('source_sha256')==stamp and evidence.get('pdk_pin')==req['pdk_version'])
        else:
            raw=ROOT/evidence.get('trace','build/openpll/missing.prn')
            check('OpenPLL physical trace fingerprint',raw.is_file() and evidence.get('input_sha256')==digest(raw))
    regression=read(bundle/'regression/summary.json' if bundle else 'build/regression/summary.json')
    check('complete extracted regression',regression.get('passed') and regression.get('complete_matrix'))
    actual={r['case']['name']:r for r in regression.get('results',[])}
    check('exact link case coverage',len(actual)==len(regression.get('results',[]))==len(matrix()) and
          set(actual)=={case['name'] for case in matrix()})
    fast_library=None
    if any(r.get('result',{}).get('network')=='TICER approximate RC' for r in actual.values()):
        try:fast_library=selected_fast if bundle else library(extracted=True,digital=True,fast=True)[0]
        except (ValueError,KeyError,FileNotFoundError):pass
    for case in matrix():
        r=actual.get(case['name'],{});s=r.get('result',{})
        circuit=fast_library if s.get('network')=='TICER approximate RC' else expected_rc
        ok,detail=link_matches(s,case,req,circuit) if circuit is not None else (False,'Missing circuit library')
        check('link/'+case['name'],r.get('passed') and r.get('case')==case and ok,detail)
        if bundle:check('bundle input/'+case['name'],s.get('config',{}).get('bundle')==str(bundle.relative_to(ROOT)) and
                        s.get('config',{}).get('bundle_manifest_sha256')==digest(bundle/'manifest.json'))
        if s.get('network')=='full distributed RC':check('RC inputs/'+case['name'],s.get('inputs')==exact)
        elif s:
            cert=read(bundle/'rc_certificate.json' if bundle else 'build/rc_validation/summary.json')
            check('RC approximation/'+case['name'],valid_certificate(cert,s.get('inputs',{})))
    if bundle:
        from phy_candidate import load
        try:check('staged six-fixture RC certificate',valid_certificate(read(bundle/'rc_certificate.json'),load(bundle,True)[1]))
        except (OSError,ValueError,KeyError,TypeError) as error:check('staged six-fixture RC certificate',False,str(error))
    out=release_out;out.mkdir(parents=True,exist_ok=True)
    result=dict(passed=all(c['passed'] for c in checks),checks=checks)
    if bundle:
        from pfd_candidate_policy import policy_provenance
        result.update(staged_context,checker_sha256=digest(Path(__file__)),
        staged_gate_sha256=digest(ROOT/'scripts/staged_release.py'),
        native_gate_sha256=digest(ROOT/'scripts/dll_native_evidence.py'),
        candidate_rtl_gate_sha256=digest(ROOT/'scripts/verify_candidate_rtl.py'),
        pfd_policy_code=policy_provenance(ROOT))
    (out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
    failed=[c['name'] for c in checks if not c['passed']]
    print(json.dumps(dict(passed=result['passed'],checks=len(checks),failed=failed),indent=2))
    return 0 if result['passed'] else 1

if __name__=='__main__':sys.exit(main())
