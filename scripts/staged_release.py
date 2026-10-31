# SPDX-License-Identifier: GPL-3.0-only
"""Additional release gates for an isolated, electrically tested OTA PHY bundle."""
import hashlib
import json
from pathlib import Path

from dll_candidate_library import assemble as assemble_dll
from dll_native_evidence import verify as verify_native
from layout import circuits,flatten
from ota_operating_points import verify as verify_operating
from phy_candidate import load
from qualify_dll_readiness import verify as verify_readiness
from qualify_dll_recovery import verify as verify_recovery
from stability_evidence import verified as verify_stability
from stage_phy_candidate import assemble as assemble_phy

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def proof_binding(path,qualification,stability=None,recovery=None):
    path=Path(path).resolve()
    if path.parent.parent.parent!=qualification:
        raise ValueError('Release proof belongs to another native DLL candidate')
    identity=json.loads((path.parent/'manifest.json').read_text())['identity']
    if stability is not None and (ROOT/identity['stability']).resolve()!=stability:
        raise ValueError('Release proof uses another stability model')
    if recovery is not None and (ROOT/identity['recovery']).resolve()!=recovery:
        raise ValueError('Readiness proof uses another recovery report')


def gates(bundle,stability,recovery,readiness,operating,check):
    bundle=Path(bundle).resolve();full,_,_=load(bundle);fast,_,_=load(bundle,True)
    identity=json.loads((bundle/'manifest.json').read_text())['identity']
    qualification=(ROOT/identity['qualification']).resolve()
    q=json.loads((qualification/'manifest.json').read_text());native=q['identity']['full_models']
    stability,recovery,readiness,operating=[Path(p).resolve() for p in [stability,recovery,readiness,operating]]
    def attempt(name,fn):
        try:fn()
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:check(name,False,str(error))
        else:check(name,True)
    def physical():
        # Rebuild from audited physical inputs; recorded success booleans alone
        # cannot establish that the staged bytes are the manufactured topology.
        layout=ROOT/native['layout'];pfd=ROOT/native['pfd']
        source=(layout/'candidate.spice').read_text();definitions=circuits(source)
        ports,devices=flatten(definitions,'openlvds_dll_analog')
        ota=[row for row in definitions['openlvds_dll_analog'][1] if row[2]=='lvds_phase_ota']
        if len(ports)!=15 or len(ota)!=1 or 'lvds_phase_ota' not in definitions or any(
            'VCOPY' in node.upper() for d in devices for node in d['nodes']):
            raise ValueError('Expected a 15-port OTA DLL without control-copy circuitry')
        for mode,expected in [(False,full),(True,fast)]:
            library,models=assemble_dll(layout,pfd,mode)
            if library!=(qualification/('fast.spice' if mode else 'full.spice')).read_text():
                raise ValueError('Native DLL library differs from current physical reconstruction')
            if models!=q['identity']['fast_models' if mode else 'full_models']:
                raise ValueError('Native DLL physical model inputs changed')
            reconstructed,info=assemble_phy(qualification,ROOT/identity['tx'],mode)
            if reconstructed.encode()!=expected or info!=identity['fast' if mode else 'full']:
                raise ValueError('PHY bundle differs from audited physical reconstruction')
    attempt('staged exact physical reconstruction and OTA topology',physical)
    attempt('complete native DLL waveform reanalysis',lambda:verify_native(qualification))
    def model():
        if stability.parent.parent.parent!=qualification:raise ValueError('Stability belongs to another candidate')
        req=json.loads((qualification/'requirements.json').read_text())
        corners=tuple(f'{p}_{t}' for p in req['process_corners'] for t in req['temperatures_c'])
        verify_stability(stability,native['inputs'],corners)
    attempt('all-PVT measured loop model and native step agreement',model)
    for name,path,verify in [('limiting-corner native recovery',recovery,verify_recovery),
                             ('native RTL readiness replay',readiness,verify_readiness),
                             ('correlated OTA operating points',operating,verify_operating)]:
        def validate_proof(path=path,verify=verify):
            proof_binding(path,qualification,stability,recovery if path==readiness else None)
            verify(path)
        attempt(name,validate_proof)
    return dict(bundle=str(bundle.relative_to(ROOT)),bundle_manifest_sha256=digest(bundle/'manifest.json'),
        qualification=str(qualification.relative_to(ROOT)),proofs={name:dict(path=str(path.relative_to(ROOT)),sha256=digest(path))
            for name,path in [('stability',stability),('recovery',recovery),('readiness',readiness),('ota_operating_points',operating)]
            if path.is_file()})
