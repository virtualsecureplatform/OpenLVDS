#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fail closed on missing, stale or failed physical/electrical evidence."""
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

ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    (ROOT/'build/release/status.json').unlink(missing_ok=True)
    checks=[];req=json.loads((ROOT/'requirements.json').read_text())
    source=digest(ROOT/'analog/openlvds.spice');requirements=digest(ROOT/'requirements.json')
    simulator_stamp=provenance();analysis_stamp=digest(ROOT/'scripts/verify_analog.py')
    def check(name,condition,detail=''):
        checks.append(dict(name=name,passed=bool(condition),detail=detail))
    def read(path):
        p=ROOT/path
        if not p.exists():check(path,False,'Missing evidence');return {}
        try:return json.loads(p.read_text())
        except ValueError:check(path,False,'Invalid JSON');return {}
    rtl=read('build/rtl/summary.json')
    check('behavioral coverage',rtl.get('passed') and not rtl.get('smoke',True) and rtl.get('total_bits',0)>=req['minimum_behavioral_bits'])
    # Recreate verify_rtl.py's source fingerprint, including its benches/models.
    sources=sorted((ROOT/'rtl').glob('*.v'))+[ROOT/'tb/tb_link.v']
    dll=[ROOT/'rtl/openlvds_dll_control.v',ROOT/'tb/tb_dll_control.v']
    phy=sorted((ROOT/'rtl').glob('*.v'))+[ROOT/'models/analog_functional.v',ROOT/'tb/tb_phy.v']
    stamp=hashlib.sha256(b''.join(p.read_bytes() for p in sources+dll+phy)+
        (ROOT/'requirements.json').read_bytes()+(ROOT/'scripts/verify_rtl.py').read_bytes()).hexdigest()
    check('behavioral source fingerprint',rtl.get('source_hash')==stamp)
    physical=read('build/layout/current.json')
    check('analog GDS DRC/LVS',physical.get('passed') and physical.get('source_sha256')==source)
    # A generator revision does not invalidate already manufactured geometry;
    # its actual extracted connectivity must pass the current LVS policy.
    for name,info in physical.get('designs',{}).items():
        out=(ROOT/info['gds']).parent
        report=out/(name+'.lvs.log')
        check(name+' strict LVS',report.exists() and clean_match(report.read_text()) and
              info.get('lvs_report_sha256')==digest(report))
    for kind in ['tx','rx','pfd']:
        evidence=read(f'build/physical/{kind}/summary.json')
        check(kind+' digital physical flow',evidence.get('passed'))
        name={'tx':'openlvds_tx_core','rx':'openlvds_ddr_rx','pfd':'lvds_pfd'}[kind]
        files=[ROOT/'rtl/openlvds_reset.v',ROOT/f'rtl/{name}.v']
        if kind=='tx':files.append(ROOT/'rtl/openlvds_ddr_tx.v')
        if kind=='pfd':files=[ROOT/'sky130/lvds_pfd.v']
        config=ROOT/f'build/physical/{kind}/config.json'
        stamp=hashlib.sha256(b''.join(p.read_bytes() for p in files)+
            (ROOT/f'constraints/{kind}.sdc').read_bytes()+config.read_bytes()).hexdigest() if config.exists() else None
        check(kind+' physical source fingerprint',evidence.get('source_sha256')==stamp and stamp is not None)
    try:
        expected_rc,exact,_=library(extracted=True,digital=True)
        check('distributed RC networks and port bindings',True)
    except (ValueError,KeyError,FileNotFoundError) as error:
        exact={};expected_rc=None;check('distributed RC networks and port bindings',False,str(error))
    audit=read('build/rc_audit/summary.json')
    for name in ['openlvds_driver_core','openlvds_receiver_core','openlvds_dll_analog','openlvds_delay_line','lvds_bias']:
        evidence=audit.get('designs',{}).get(name,{})
        report=ROOT/evidence.get('report','build/rc_audit/missing.log')
        check('RC topology/'+name,evidence.get('passed') and exact.get(name) is not None and
            evidence.get('netlist_sha256')==exact[name] and report.is_file() and
            evidence.get('report_sha256')==digest(report) and clean_match(report.read_text()))
    for root in ['analog','analog_extracted']:
        for test in ['driver','receiver','receiver_rate','dll']:
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
    regression=read('build/regression/summary.json')
    check('complete extracted regression',regression.get('passed') and regression.get('complete_matrix'))
    actual={r['case']['name']:r for r in regression.get('results',[])}
    fast_library=None
    if any(r.get('result',{}).get('network')=='TICER approximate RC' for r in actual.values()):
        try:fast_library=library(extracted=True,digital=True,fast=True)[0]
        except (ValueError,KeyError,FileNotFoundError):pass
    for case in matrix():
        r=actual.get(case['name'],{});s=r.get('result',{})
        circuit=fast_library if s.get('network')=='TICER approximate RC' else expected_rc
        ok,detail=link_matches(s,case,req,circuit) if circuit is not None else (False,'Missing circuit library')
        check('link/'+case['name'],r.get('passed') and r.get('case')==case and ok,detail)
        if s.get('network')=='full distributed RC':check('RC inputs/'+case['name'],s.get('inputs')==exact)
        elif s:
            cert=read('build/rc_validation/summary.json')
            check('RC approximation/'+case['name'],valid_certificate(cert,s.get('inputs',{})))
    out=ROOT/'build/release';out.mkdir(parents=True,exist_ok=True)
    result=dict(passed=all(c['passed'] for c in checks),checks=checks)
    (out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
    failed=[c['name'] for c in checks if not c['passed']]
    print(json.dumps(dict(passed=result['passed'],checks=len(checks),failed=failed),indent=2))
    return 0 if result['passed'] else 1

if __name__=='__main__':sys.exit(main())
