#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Continue the corrected DLL through unchanged recovery, readiness and OTA gates."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
import continue_dll_storage_full as full

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
PHASES = ('recovery', 'readiness', 'ota')
SCOPES = dict(recovery='recovery', readiness='readiness', ota='ota_operating_points')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(prerequisite, unit):
    full.relative(str(prerequisite.relative_to(ROOT)), 'dll_storage_full_followup')
    parent = json.loads((prerequisite/'manifest.json').read_text())['identity']
    qualification = ROOT/full.relative(parent['qualification'], 'dll_qualification')
    q = json.loads((qualification/'manifest.json').read_text())
    if q['identity'].get('variant') != full.VARIANT or len(q['tasks']) != 336:
        raise ValueError('Require the corrected 336-case DLL qualification')
    live = full.owner(unit)
    if live['ActiveState'] != 'active' or live['MainPID'] == '0':
        raise ValueError('Require the exact live full-DLL continuation owner')
    paths = [prerequisite/'manifest.json']
    paths += [qualification/n for n in ['manifest.json', 'full.spice', 'fast.spice', 'requirements.json', 'storage_source_admission.json']]
    paths += [ROOT/'scripts'/n for n in [NAME, 'continue_dll_storage_full.py', 'qualify_dll_storage.py',
        'measure_dll_storage_stability.py', 'qualify_dll_candidate.py', 'qualify_dll_recovery.py',
        'qualify_dll_readiness.py', 'ota_operating_points.py', 'dll_signoff_cases.py',
        'dll_readiness_replay.py', 'measure_dll_stability.py', 'stability_evidence.py',
        'spice_dispatch.py', 'env.sh']]
    paths += [ROOT/'rtl/openlvds_dll_control.v']
    identity = dict(prerequisite=str(prerequisite.relative_to(ROOT)), qualification=str(qualification.relative_to(ROOT)),
        unit=unit, owner=live, files={str(p.relative_to(ROOT)):sha(p) for p in paths},
        max_workers=3, no_outer_lease=True, qualified_phy=False,
        scope='Resource/variant adapter only: all 336 native cases and all fifteen measured stability corners precede original limiting-corner recovery, native-waveform RTL readiness with late clock loss, and guarded OTA gm/offset/stress characterization. Fixed supplies and original fixtures/limits retained. RC and integrated PHY qualification remain separate.')
    out = ROOT/'build/diagnostics/dll_storage_signoff_followup'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out/'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def admission(qualification, row):
    if (row.get('native_full_passed') is not True or row.get('all_pvt_stability_passed') is not True or
            row.get('qualification') != str(qualification.relative_to(ROOT)) or
            row.get('native_report_sha256') != sha(qualification/'summary.json')):
        raise ValueError('Require the exact completed native and all-PVT stability handoff')
    report = ROOT/full.relative(row['all_pvt_stability'], 'dll_qualification')
    if sha(report) != row['all_pvt_stability_sha256']:
        raise ValueError('All-PVT stability handoff changed')
    q = json.loads((qualification/'manifest.json').read_text())
    if row.get('full_inputs') != q['identity']['full_models']['inputs']:
        raise ValueError('Signoff handoff selected other native inputs')
    full.full_native(qualification)
    full.all_pvt(qualification, report)
    return report


def fresh_scope(qualification, phase):
    if phase not in PHASES:
        raise ValueError('Unknown storage signoff phase')
    scope = qualification/SCOPES[phase]
    if scope.exists() and any(scope.iterdir()):
        raise ValueError('Prior '+phase+' output retained; no automatic overwrite or partial retry')


@contextmanager
def resources():
    import qualify_dll_storage as storage
    import measure_dll_storage_stability as stability
    import ota_operating_points as ota
    from spice_dispatch import lease
    previous = ota.slot
    try:
        ota.slot = lambda: lease(ROOT, priority=1, label='dll_storage_ota_operating_points')
        with storage.profile(), stability.resources():
            yield
    finally:
        ota.slot = previous


def execute(phase, qualification, stability, recovery=None):
    import qualify_dll_recovery as recovery_engine
    import qualify_dll_readiness as readiness_engine
    import ota_operating_points as ota
    full.relative(str(qualification.relative_to(ROOT)), 'dll_qualification')
    q = json.loads((qualification/'manifest.json').read_text())
    if q['identity'].get('variant') != full.VARIANT:
        raise ValueError('Require the corrected storage DLL variant')
    full.full_native(qualification)
    full.all_pvt(qualification, stability)
    with (qualification/'.storage_signoff.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fresh_scope(qualification, phase)
        with resources():
            # Original producers validate every native/stability input and run
            # their original reanalysis before returning success.
            if phase == 'recovery':
                result = recovery_engine.run(qualification, stability, jobs=3)
            elif phase == 'readiness':
                if recovery is None:
                    raise ValueError('Readiness requires completed native recovery')
                recovery_engine.verify(recovery)
                result = readiness_engine.run(qualification, stability, recovery, jobs=3)
            elif phase == 'ota':
                result = ota.run(qualification, stability, jobs=3)
            else:
                raise ValueError('Unknown storage signoff phase')
            if result != 0:
                raise ValueError('Original '+phase+' gate failed')


def result_path(qualification, phase, line):
    inside = Path(line)
    if not inside.is_relative_to('/work/OpenLVDS'):
        raise ValueError('Unexpected storage signoff result path')
    report = ROOT/inside.relative_to('/work/OpenLVDS')
    if (not report.is_relative_to(qualification/SCOPES[phase]) or report.name != 'summary.json' or
            json.loads(report.read_text()).get('passed') is not True):
        raise ValueError('Failed or unrelated storage signoff report')
    return report


def run(out):
    full.relative(str(out.relative_to(ROOT)), 'dll_storage_signoff_followup')
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']; stamp = sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json') != stamp or i.get('max_workers') != 3 or i.get('no_outer_lease') is not True or
                any(sha(ROOT/n) != h for n,h in i['files'].items())):
            raise ValueError('Storage signoff resource context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        if (out/'state.json').exists():
            raise ValueError('Prior signoff context retained')
        try:
            prerequisite = ROOT/i['prerequisite']; receipt = prerequisite/'summary.json'
            while not receipt.is_file():
                unchanged(); live = full.owner(i['unit'])
                if live != i['owner']:
                    if receipt.is_file(): break
                    raise ValueError('Full-DLL owner terminated before completed evidence')
                state = prerequisite/'state.json'
                if state.exists() and json.loads(state.read_text()).get('status') == 'held_for_diagnosis':
                    raise ValueError('Full-DLL continuation held for diagnosis')
                atomic(out/'state.json', dict(status='waiting_full_native_and_all_pvt_stability', owner=live, qualified_phy=False))
                time.sleep(20)
            qualification = ROOT/i['qualification']
            row = json.loads(receipt.read_text())
            if row.get('manifest_sha256') != sha(prerequisite/'manifest.json'):
                raise ValueError('Full-DLL handoff manifest changed')
            stability = admission(qualification, row)
            capture_manifest(out/'admission.json', dict(receipt_sha256=sha(receipt), stability_sha256=sha(stability), qualified_phy=False))
            reports = {}
            for phase in PHASES:
                unchanged(); fresh_scope(qualification, phase)
                atomic(out/'state.json', dict(status='running_'+phase, qualified_phy=False))
                args = [str(ROOT/'scripts/env.sh'), '--ngspice', '/usr/bin/python3', 'scripts/'+NAME,
                    'execute', phase, i['qualification'], '--stability', str(stability.relative_to(ROOT))]
                if phase == 'readiness':
                    args += ['--recovery', reports['recovery']['report']]
                with (out/(phase+'.log')).open('w') as log:
                    subprocess.run(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
                unchanged()
                report = result_path(qualification, phase, (out/(phase+'.log')).read_text().strip().splitlines()[-1])
                reports[phase] = dict(report=str(report.relative_to(ROOT)), sha256=sha(report))
                capture_manifest(out/(phase+'_result.json'), dict(reports[phase], passed=True, qualified_phy=False))
            if any(sha(ROOT/r['report']) != r['sha256'] for r in reports.values()):
                raise ValueError('Storage signoff reports changed')
            unchanged()
            capture_manifest(out/'summary.json', dict(passed=True, qualification=i['qualification'], reports=reports,
                manifest_sha256=stamp, qualified_phy=False, scope=i['scope']))
            atomic(out/'state.json', dict(status='recovery_readiness_ota_passed', qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json', dict(status='held_for_diagnosis', error=str(error), qualified_phy=False))
            raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare'); a.add_argument('prerequisite', type=Path); a.add_argument('--producer-unit', required=True)
    a = sub.add_parser('run'); a.add_argument('artifact', type=Path)
    a = sub.add_parser('execute'); a.add_argument('phase', choices=PHASES); a.add_argument('qualification', type=Path)
    a.add_argument('--stability', required=True, type=Path); a.add_argument('--recovery', type=Path)
    a = p.parse_args()
    if a.action == 'prepare': print(prepare(a.prerequisite.resolve(), a.producer_unit), flush=True)
    elif a.action == 'run': run(a.artifact.resolve())
    else: execute(a.phase, a.qualification.resolve(), a.stability.resolve(), a.recovery.resolve() if a.recovery else None)
