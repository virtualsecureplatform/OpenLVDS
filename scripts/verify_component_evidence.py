#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify current component proofs separately from historical batch exit codes."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from dll_campaign import atomic
from evidence_scope import matches
from spice_engine import engine, provenance
from spice_library import library

ROOT=Path(__file__).resolve().parents[1]
TESTS={'driver':{'lvds_bias','openlvds_driver_core'},
       'receiver':{'lvds_bias','openlvds_receiver_core'},
       'receiver_rate':{'lvds_bias','openlvds_receiver_core'}}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def cases(requirements):
    return [(view,test,corner,temp) for view in ['analog','analog_extracted'] for test in TESTS
        for corner in requirements['process_corners'] for temp in requirements['temperatures_c']]


def check_case(folder,test,source,inputs,analysis,requirements,simulator,stamp):
    if not folder.exists():return dict(status='missing',passed=False)
    # NFS shared advisory locks require a descriptor open for reading.
    with (folder/'.run.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:return dict(status='running',passed=False)
        report=folder/'summary.json'
        if not report.exists():return dict(status='missing',passed=False)
        try:
            evidence=json.loads(report.read_text());scope='receiver' if test=='receiver_rate' else test
            checks=dict(measurement=evidence.get('passed') is True,
                requirements=evidence.get('requirements_sha256')==requirements,
                simulator=evidence.get('simulator')==simulator and evidence.get('simulator_provenance')==stamp,
                source=matches(evidence,folder/'source.spice',source,scope),
                extraction=evidence.get('extraction_inputs',{})==inputs,
                analysis=evidence.get('analysis_runner_sha256')==analysis,
                settled=evidence.get('startup')=='solved fixed-supply DC operating point')
            files={}
            for name,key in [('bench.cir','deck_sha256'),('bench.cir.prn','waveform_sha256'),('runner.py','runner_sha256')]:
                path=folder/name;actual=digest(path) if path.exists() else None
                checks[name]=actual is not None and actual==evidence.get(key)
                if actual:files[name]=actual
            checks['analysis_snapshot']=(files.get('runner.py')==analysis or
                ((folder/'analysis_runner.py').is_file() and digest(folder/'analysis_runner.py')==analysis))
            if test=='driver':checks['dc_output']=evidence.get('dc_output',{}).get('passed') is True
            passed=all(checks.values());files['summary.json']=digest(report)
            return dict(status='passed' if passed else 'failed_or_stale',passed=passed,checks=checks,files=files)
        except (OSError,ValueError,KeyError,TypeError) as error:
            return dict(status='invalid',passed=False,error=str(error))


def verify():
    requirements=ROOT/'requirements.json';req=json.loads(requirements.read_text())
    captured=dict(requirements_sha256=digest(requirements),analysis_sha256=digest(ROOT/'scripts/verify_analog.py'),
        producer_sha256=digest(Path(__file__)),simulator=engine(),simulator_provenance=provenance())
    source=(ROOT/'analog/openlvds.spice').read_bytes();expected={}
    for test,designs in TESTS.items():
        text,inputs,_=library(extracted=True,designs=designs);expected[test]=(text,inputs)
    results=[]
    for view,test,corner,temp in cases(req):
        relative=f'build/{view}/{test}_{corner}_{temp}'
        text,inputs=expected[test] if view=='analog_extracted' else (source,{})
        proof=check_case(ROOT/relative,test,text,inputs,captured['analysis_sha256'],
            captured['requirements_sha256'],captured['simulator'],captured['simulator_provenance'])
        results.append(dict(case=relative,**proof))
    unchanged=(digest(requirements)==captured['requirements_sha256'] and
        digest(ROOT/'scripts/verify_analog.py')==captured['analysis_sha256'] and
        digest(Path(__file__))==captured['producer_sha256'] and provenance()==captured['simulator_provenance'] and
        (ROOT/'analog/openlvds.spice').read_bytes()==source)
    for test,designs in TESTS.items():
        text,inputs,_=library(extracted=True,designs=designs)
        unchanged &= (text,inputs)==expected[test]
    return dict(passed=unchanged and all(r['passed'] for r in results),qualified_phy=False,
        scope='Current schematic/native driver and analog receiver component evidence only; no DLL, aperture or link qualification',
        identity=captured,inputs_unchanged=bool(unchanged),required=len(cases(req)),
        passed_cases=sum(r['passed'] for r in results),cases=results)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'build/diagnostics/component_refresh/current_evidence.json')
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'build/diagnostics'):raise ValueError('Keep receipts under build/diagnostics')
    result=verify();out.parent.mkdir(parents=True,exist_ok=True);atomic(out,result)
    print(f'{out}: {result["passed_cases"]}/{result["required"]} current proofs pass',flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
