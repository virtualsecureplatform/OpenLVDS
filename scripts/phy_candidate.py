# SPDX-License-Identifier: GPL-3.0-only
"""Load an immutable staged PHY without changing the active extraction pointers."""
import hashlib
import json
from pathlib import Path
from qualify_dll_candidate import validate, evaluate
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def load(bundle,fast=False):
    root=Path(bundle).resolve()
    if not root.is_relative_to(ROOT/'build/diagnostics/phy_candidate'):
        raise ValueError('PHY bundle outside the isolated candidate directory')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    if (identity['producer_sha256']!=digest(ROOT/'scripts/stage_phy_candidate.py') or
        identity['requirements_sha256']!=digest(ROOT/'requirements.json')):
        raise ValueError('PHY bundle producer or requirements changed')
    if identity.get('rx'):
        from rx_candidate_aperture import extra_code
        if identity.get('rx_producer_code')!=extra_code():raise ValueError('PHY RX producer changed')
    qualification=(ROOT/identity['qualification']).resolve()
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Invalid DLL qualification path')
    if digest(qualification/'manifest.json')!=identity['qualification_manifest_sha256']:
        raise ValueError('PHY bundle DLL manifest changed')
    validate(qualification,json.loads((qualification/'manifest.json').read_text()))
    for info in [identity['full'],identity['fast']]:
        for name,value in info['physical_reports'].items():
            source=(ROOT/name).resolve()
            if not source.is_relative_to(ROOT) or digest(source)!=value:
                raise ValueError('PHY bundle physical evidence changed')
    mode='fast' if fast else 'full';info=identity[mode]
    path=root/(mode+'.spice')
    if digest(path)!=identity[mode+'_sha256']:raise ValueError('PHY bundle library changed')
    data=path.read_bytes()
    for name,value in info['scopes'].items():
        if closure_hash(data,name)!=value:raise ValueError('PHY bundle circuit scope changed')
    return data,info['inputs'],info['digital_models']


def phase(bundle,process,temperature,mhz,duty):
    """Use only the exact native-RC case for the requested phase partition."""
    root=Path(bundle).resolve();load(root)
    identity=json.loads((root/'manifest.json').read_text())['identity']
    qualification=ROOT/identity['qualification']
    manifest=json.loads((qualification/'manifest.json').read_text())
    if closure_hash((root/'full.spice').read_bytes(),'openlvds_dll')!=closure_hash((qualification/'full.spice').read_bytes(),'openlvds_dll'):
        raise ValueError('Staged DLL differs from the characterized native circuit')
    selected=[]
    for task in manifest['tasks']:
        spec=task['spec']
        if (not task['fast_rc'] and spec['kind']=='loop' and not spec.get('step_mhz') and
            not spec.get('interruption') and spec['process']==process and spec['temperature']==temperature and
            abs(spec['mhz']-mhz)<1e-9 and abs(spec['duty']-duty)<5e-7):selected.append(task)
    if len(selected)!=1:raise ValueError('Missing or ambiguous native DLL phase case')
    task=selected[0];folder=qualification/task['id']
    report=json.loads((folder/'summary.json').read_text())
    if (not report.get('passed') or report['deck_sha256']!=digest(folder/'bench.cir') or
        task['deck_sha256']!=report['deck_sha256'] or report['waveform_sha256']!=digest(folder/'bench.cir.prn')):
        raise ValueError('Native DLL phase evidence changed or failed')
    measured=evaluate(qualification,task)
    if not measured['passed'] or measured!=report['metrics']:raise ValueError('Native DLL phase reanalysis failed')
    return dict(quarter_phase_min_ps=measured['quarter_phase_min_ps'],
        quarter_phase_max_ps=measured['quarter_phase_max_ps'],clock_duty=duty,
        evidence_sha256=digest(folder/'summary.json'),task=task['id'])
