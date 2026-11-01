# SPDX-License-Identifier: GPL-3.0-only
"""Bind selected-library clock replay to its exact completed native DLL case."""
import json
from pathlib import Path
import selected_phy
from qualify_dll_candidate import evaluate
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]


def phase(bundle,process,temperature,mhz,duty):
    root=Path(bundle).resolve();data,_,_=selected_phy.load(root)
    identity=json.loads((root/'manifest.json').read_text())['identity']
    qualification=(ROOT/identity['paths']['qualification']).resolve()
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Invalid selected DLL qualification path')
    source=(qualification/'full.spice').read_bytes()
    for top in ['openlvds_dll','lvds_bias']:
        if closure_hash(data,top)!=closure_hash(source,top):raise ValueError('Selected phase circuit changed: '+top)
    manifest=json.loads((qualification/'manifest.json').read_text());selected=[]
    for task in manifest['tasks']:
        s=task['spec']
        if (not task['fast_rc'] and s['kind']=='loop' and not s.get('step_mhz') and not s.get('interruption') and
                s['process']==process and s['temperature']==temperature and abs(s['mhz']-mhz)<1e-9 and abs(s['duty']-duty)<5e-7):
            selected.append(task)
    if len(selected)!=1:raise ValueError('Missing or ambiguous selected native DLL phase case')
    task=selected[0];folder=qualification/task['id'];report=json.loads((folder/'summary.json').read_text())
    sha=selected_phy.digest
    if (report.get('passed') is not True or report['deck_sha256']!=sha(folder/'bench.cir') or
            report['deck_sha256']!=task['deck_sha256'] or report['waveform_sha256']!=sha(folder/'bench.cir.prn')):
        raise ValueError('Selected DLL phase evidence changed or failed')
    measured=evaluate(qualification,task)
    if not measured['passed'] or measured!=report['metrics']:raise ValueError('Selected DLL phase reanalysis failed')
    lo,hi=measured['quarter_phase_min_ps'],measured['quarter_phase_max_ps']
    if not 0<=lo<=hi:raise ValueError('Invalid selected DLL phase range')
    return dict(quarter_phase_min_ps=lo,quarter_phase_max_ps=hi,clock_duty=duty,
        evidence_sha256=sha(folder/'summary.json'),task=task['id'],qualification=str(qualification.relative_to(ROOT)))
