# SPDX-License-Identifier: GPL-3.0-only
"""Validate measured stability evidence before expanding a native campaign."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PRODUCERS={'measure_dll_stability.py','dll_stability.py','native_ac.py','spice_slots.py','qualify_dll_candidate.py','dll_measurements.py'}
MEASUREMENTS={'instrument.spice',*[f'ac_{clock}_{mode}/bench.raw' for clock in ['0','1.8'] for mode in ['g','y']],
              *[f'delay_{i}/bench.cir.prn' for i in range(3)],*[f'step_{mhz}/bench.cir.prn' for mhz in [390,410]]}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verified(path,inputs,corners=('ss_0','tt_25','ff_0')):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Stability report outside candidate qualification artifacts')
    report=json.loads(path.read_text());root=path.parent
    manifest=json.loads((root/'manifest.json').read_text())
    qualification=root.parent.parent
    if manifest['qualification_manifest_sha256']!=digest(qualification/'manifest.json') or manifest['library_sha256']!=digest(qualification/'full.spice'):
        raise ValueError('Stability candidate source changed')
    if not (report.get('passed') and report['full_inputs']==inputs==manifest['full_inputs'] and
            report['manifest_sha256']==digest(root/'manifest.json')):
        raise ValueError('Failed or stale stability model')
    from spice_engine import provenance
    if report['simulator_provenance']!=provenance():raise ValueError('Stability simulator changed')
    if set(manifest['code'])!=PRODUCERS or report['producer_sha256']!=manifest['code']['measure_dll_stability.py']:
        raise ValueError('Stability producer attestation incomplete')
    for name,value in manifest['code'].items():
        if digest(ROOT/'scripts'/name)!=value:raise ValueError('Stability producer changed')
    actual={r['corner']:r for r in report['results']}
    if len(actual)!=len(report['results']) or set(actual)!=set(corners):raise ValueError('Incomplete stability corners')
    phase=[];gain=[]
    for result in actual.values():
        if not MEASUREMENTS<=set(result['files']) or len(result['source_reports'])!=6:
            raise ValueError('Stability measurement set incomplete')
        for filename,value in result['source_reports'].items():
            source=qualification/filename
            if not source.resolve().is_relative_to(qualification) or digest(source)!=value:
                raise ValueError('Stability operating-point evidence changed')
        if not result['passed'] or len(result['models'])!=3:raise ValueError('Incomplete clock-state models')
        for model in result['models']:
            if not (model['passed'] and model['model_valid'] and model['phase_margin_min_deg']>=60 and model['gain_margin_min_db']>=6):
                raise ValueError('Loop-margin gate failed')
            phase.append(model['phase_margin_min_deg']);gain.append(model['gain_margin_min_db'])
        validation=result['transient_validation']
        if len(validation)!=2 or {v['target_mhz'] for v in validation}!={390,410}:
            raise ValueError('Missing native step validation')
        if any(not v['passed'] or not 0<=v['amplitude_relative_error']<=.25 or
               not 0<=v['settling_relative_error']<=.25 for v in validation):
            raise ValueError('Measured/model response disagreement')
        for filename,value in result['files'].items():
            source=root/result['corner']/filename
            if not source.resolve().is_relative_to(root) or digest(source)!=value:
                raise ValueError('Stability measurement artifact changed')
    if min(phase)!=report['phase_margin_min_deg'] or min(gain)!=report['gain_margin_min_db']:
        raise ValueError('Stability summary differs from measured corner models')
    return report
