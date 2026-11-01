#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Resume unchanged aperture science with a shared lease per uncached point."""
import argparse,fcntl,hashlib,json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import rx_candidate_aperture as campaign
from rx_aperture_evidence import verify_witness
from receiver_static_diagnosis import capture_manifest
from dll_campaign import atomic
import spice_dispatch
ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def completed(root,manifest,spec):
    path=root/campaign.capture.condition_id(spec)/'summary.json'
    if not path.exists():return None
    result=json.loads(path.read_text())
    if result.get('passed') is not True:return None
    if (result['spec']!=spec or not 0<result['passed_ps']-result['failed_ps']<=5 or
            result['bound_ps']!=campaign.capture.guarded_bound(result['passed_ps']) or result['guard_ps']!=20 or
            result['resolution_ps']!=result['passed_ps']-result['failed_ps']):raise ValueError('Completed aperture boundary changed')
    for distance,passed in [(result['failed_ps'],False),(result['passed_ps'],True),(result['bound_ps'],True)]:
        verify_witness(root,manifest,spec,distance,passed)
    return result


def point_with_lease(root,manifest,spec,distance,original,unchanged):
    unchanged();out=root/campaign.capture.condition_id(spec)/('point_'+f'{distance:.6f}'.replace('-','m').replace('.','p'))
    if (out/'summary.json').exists():return original(root,manifest,spec,distance)
    if any((out/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):raise ValueError('Partial aperture point retained; do not restart it')
    with spice_dispatch.lease(ROOT,priority=2,label=campaign.capture.condition_id(spec)):
        unchanged();return original(root,manifest,spec,distance)


def run(root,jobs=2):
    if type(jobs) is not int or jobs not in range(1,4):raise ValueError('Use one through three aperture workers')
    if not root.is_relative_to(ROOT/'build/characterization/rx_aperture'):raise ValueError('Use an existing captured RX aperture context')
    manifest=json.loads((root/'manifest.json').read_text());campaign.validate(root,manifest)
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        policy=dict(manifest_sha256=digest(root/'manifest.json'),jobs=jobs,global_slot_budget=6,
            lease_scope='one uncached point; cached scientific witnesses require no simulation lease',
            priority=2,aging_seconds=spice_dispatch.AGING_SECONDS,legacy_handoff_seconds=spice_dispatch.LEGACY_HANDOFF_SECONDS,
            code={n:digest(ROOT/'scripts'/n) for n in ['continue_rx_aperture_fair.py','spice_dispatch.py']})
        schedule=root/'execution_scheduling'/hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()[:16]
        schedule.mkdir(parents=True,exist_ok=True);capture_manifest(schedule/'manifest.json',policy)
        def unchanged():
            campaign.validate(root,manifest)
            if digest(root/'manifest.json')!=policy['manifest_sha256'] or any(digest(ROOT/'scripts'/n)!=h for n,h in policy['code'].items()):raise ValueError('Aperture continuation context changed')
        original=campaign.capture.point;failed=Event()
        def point(folder,context,spec,distance):
            return point_with_lease(folder,context,spec,distance,original,unchanged)
        campaign.capture.point=point
        try:
            campaign.check_seeds(root,manifest)
            atomic(root/'state.json',dict(status='running_full',max_jobs=jobs,qualified_phy=False,resource_policy=str(schedule.relative_to(ROOT))))
            def worker(spec):
                if failed.is_set():return dict(spec=spec,passed=False,held=True)
                unchanged();result=completed(root,manifest,spec)
                if result is None:result=campaign.capture.search(root,manifest,spec)
                if not result['passed']:failed.set()
                unchanged();return result
            with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(worker,campaign.ordered_conditions(manifest['conditions'])))
            unchanged()
            if any(r.get('held') or not r['passed'] for r in results):
                atomic(schedule/'incomplete_summary.json',dict(passed=False,results=results,qualified_phy=False))
                atomic(root/'state.json',dict(status='held_by_native_failure',passed=False,qualified_phy=False));return 1
            result=campaign.table(manifest,results,json.loads((root/'requirements.json').read_text()),digest(root/'manifest.json'))
            atomic(root/'table.json',result);atomic(root/'state.json',dict(status='complete',passed=result['passed'],qualified_phy=False))
            return 0 if result['passed'] else 1
        except Exception as error:
            atomic(root/'state.json',dict(status='held_for_diagnosis',error=str(error),qualified_phy=False));raise
        finally:campaign.capture.point=original


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--jobs',type=int,default=2);a=p.parse_args()
    raise SystemExit(run(a.artifact.resolve(),a.jobs))
