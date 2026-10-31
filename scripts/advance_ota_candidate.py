#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Advance an audited OTA layout through native qualification and staged PHY tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from dll_campaign import atomic
from stability_evidence import PRODUCERS,verified as verify_stability

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_LAYOUT=ROOT/'build/diagnostics/dll_layout/c465a14562c2ff4f'
DEFAULT_SCREEN=ROOT/'build/diagnostics/dll_architecture/6d99d42cf3eb5d31'
DEFAULT_PFD=ROOT/'build/diagnostics/pfd_area_physical'


def qualification_config(old,relative):
    result=dict(old)
    if result.get('ota_qualification')!=relative:
        result.pop('ota_stage',None);result.pop('ota_stability',None)
        result.pop('ota_hold_reason',None)
        result['disabled']=[name for name in result.get('disabled',[]) if name!='qualify_ota']
    result.update(disabled=sorted(set(result.get('disabled',[]))|{'qualify_cp'}),ota_qualification=relative)
    return result


def cached_model(root,inputs,corners):
    code={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in PRODUCERS}
    reports=sorted(root.glob('*/summary.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    for path in reports:
        captured=json.loads((path.parent/'manifest.json').read_text())
        if captured['code']!=code:continue
        # Current-producer evidence must verify as captured. Never overwrite a
        # failed or damaged current generation to hide a rejection on restart.
        verify_stability(path,inputs,corners)
        return path
    return None


def advance(LAYOUT, screen=DEFAULT_SCREEN, pfd=DEFAULT_PFD):
    if not LAYOUT.is_relative_to(ROOT/'build/diagnostics/dll_layout'):
        raise ValueError('Use an isolated DLL layout')
    if not pfd.is_relative_to(ROOT/'build/diagnostics'):
        raise ValueError('Use an isolated PFD physical artifact')
    if LAYOUT!=DEFAULT_LAYOUT and not (LAYOUT/'rc_audit.json').exists():
        raise ValueError('Prepare and independently audit the alternate layout first')
    os.environ['OPENLVDS_SPICE']='ngspice'
    while not (LAYOUT/'rc_audit.json').exists():
        state=subprocess.run(['systemctl','--user','is-active','openlvds-w8c4-rc.service'],capture_output=True,text=True)
        if state.stdout.strip() in ['failed','inactive']:
            raise RuntimeError('Extraction ended without an audit; inspect systemd journal')
        time.sleep(10)
    if not json.loads((LAYOUT/'rc_audit.json').read_text())['passed']:
        raise RuntimeError('W8/C4 RC connectivity audit failed')
    command=['scripts/env.sh','--ngspice','python3','scripts/qualify_dll_candidate.py','prepare',
        '--layout',str(LAYOUT.relative_to(ROOT)),'--pfd',str(pfd.relative_to(ROOT)),
        '--screen',str(screen.relative_to(ROOT)),'--variant','ota_w8_c4']
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    (LAYOUT/'qualification_prepare.log').write_text(result.stdout+result.stderr)
    result.check_returncode()
    inside=Path(result.stdout.strip().splitlines()[-1]);relative=inside.relative_to('/work/OpenLVDS')
    artifact=ROOT/relative
    if not (artifact/'manifest.json').is_file():raise ValueError('Prepared manifest missing')
    from dll_native_evidence import architecture_sources
    architecture_sources(artifact,json.loads((artifact/'manifest.json').read_text()))
    config=ROOT/'build/diagnostics/resident_jobs/config.json'
    old=json.loads(config.read_text()) if config.exists() else {}
    old=qualification_config(old,str(relative))
    if 'qualify_ota' in old['disabled']:
        raise ValueError('This candidate remains held: '+old.get('ota_hold_reason','inspect resident configuration'))
    atomic(config,old)
    print('Registered OTA extracted screen:',relative,flush=True)
    workflow=LAYOUT/'workflow.json'
    def wait_for(statuses):
        while True:
            state=json.loads((artifact/'state.json').read_text())
            atomic(workflow,dict(status='waiting_for_'+','.join(statuses),qualification=str(relative),observed=state['status']))
            if state['status'] in statuses:return state['status']
            if state['status'] in ['completed_with_failures','rejected_by_architecture_screen']:
                atomic(workflow,dict(status='candidate_requires_diagnosis',qualification=str(relative),observed=state['status']))
                raise RuntimeError('OTA electrical gate failed; retain candidate for diagnosis')
            time.sleep(10)
    wait_for(['screen_passed','completed'])
    def model(all_pvt=False):
        inputs=json.loads((artifact/'manifest.json').read_text())['identity']['full_models']['inputs']
        corners=('ss_0','tt_25','ff_0')
        if all_pvt:
            req=json.loads((artifact/'requirements.json').read_text());corners=tuple(f'{p}_{t}' for p in req['process_corners'] for t in req['temperatures_c'])
        cached=cached_model(artifact/('stability_all_pvt' if all_pvt else 'stability_screen'),inputs,corners)
        if cached:return cached
        args=['scripts/env.sh','--ngspice','python3','scripts/measure_dll_stability.py',str(relative)]
        if all_pvt:args+=['--all-pvt']
        result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
        (LAYOUT/('stability_all.log' if all_pvt else 'stability_screen.log')).write_text(result.stdout+result.stderr)
        result.check_returncode()
        report=ROOT/Path(result.stdout.strip().splitlines()[-1]).relative_to('/work/OpenLVDS')
        if not json.loads(report.read_text())['passed']:
            atomic(workflow,dict(status='stability_requires_diagnosis',report=str(report.relative_to(ROOT))))
            raise RuntimeError('Measured stability or model validation failed')
        verify_stability(report,inputs,corners)
        return report
    report=model()
    old=json.loads(config.read_text());old.update(ota_stage='full',ota_stability=str(report.relative_to(ROOT)))
    atomic(config,old)
    wait_for(['completed'])
    report=model(True)
    atomic(workflow,dict(status='characterizing_observed_ota_points',qualification=str(relative),qualified_phy=False))
    result=subprocess.run(['scripts/env.sh','--ngspice','python3','scripts/ota_operating_points.py',str(relative),
        '--stability',str(report.relative_to(ROOT)),'--jobs','6'],cwd=ROOT,capture_output=True,text=True)
    (LAYOUT/'ota_operating_points.log').write_text(result.stdout+result.stderr);result.check_returncode()
    operating=ROOT/Path(result.stdout.strip().splitlines()[-1]).relative_to('/work/OpenLVDS')
    if not json.loads(operating.read_text())['passed']:raise ValueError('Observed OTA operating range failed')
    atomic(workflow,dict(status='qualifying_limiting_corner_recovery',qualification=str(relative),qualified_phy=False))
    result=subprocess.run(['scripts/env.sh','--ngspice','python3','scripts/qualify_dll_recovery.py',str(relative),
        '--stability',str(report.relative_to(ROOT)),'--jobs','6'],cwd=ROOT,capture_output=True,text=True)
    (LAYOUT/'limiting_recovery.log').write_text(result.stdout+result.stderr);result.check_returncode()
    recovery=ROOT/Path(result.stdout.strip().splitlines()[-1]).relative_to('/work/OpenLVDS')
    if not json.loads(recovery.read_text())['passed']:raise ValueError('Limiting-corner native recovery failed')
    atomic(workflow,dict(status='qualifying_native_readiness',qualification=str(relative),qualified_phy=False))
    result=subprocess.run(['scripts/env.sh','--ngspice','python3','scripts/qualify_dll_readiness.py',str(relative),
        '--stability',str(report.relative_to(ROOT)),'--recovery',str(recovery.relative_to(ROOT)),'--jobs','6'],
        cwd=ROOT,capture_output=True,text=True)
    (LAYOUT/'native_readiness.log').write_text(result.stdout+result.stderr);result.check_returncode()
    readiness=ROOT/Path(result.stdout.strip().splitlines()[-1]).relative_to('/work/OpenLVDS')
    if not json.loads(readiness.read_text())['passed']:raise ValueError('Native readiness replay failed')
    result=subprocess.run(['scripts/env.sh','--ngspice','python3','scripts/stage_phy_candidate.py',str(relative)],
        cwd=ROOT,capture_output=True,text=True)
    (LAYOUT/'bundle_prepare.log').write_text(result.stdout+result.stderr);result.check_returncode()
    bundle=ROOT/Path(result.stdout.strip().splitlines()[-1]).relative_to('/work/OpenLVDS')
    if not (bundle/'manifest.json').is_file():raise ValueError('Staged PHY manifest missing')
    def bundle_job(status,script,args,log,use_tools=False):
        atomic(workflow,dict(status=status,qualification=str(relative),bundle=str(bundle.relative_to(ROOT)),qualified_phy=False))
        result=subprocess.run(['scripts/env.sh']+(['--tools'] if use_tools else [])+
            ['--ngspice','/usr/bin/python3','scripts/'+script]+args,
            cwd=ROOT,capture_output=True,text=True)
        (LAYOUT/log).write_text(result.stdout+result.stderr)
        if result.returncode:
            atomic(workflow,dict(status=status+'_requires_diagnosis',bundle=str(bundle.relative_to(ROOT)),log=str((LAYOUT/log).relative_to(ROOT)),qualified_phy=False))
            result.check_returncode()
        return result
    relative_bundle=str(bundle.relative_to(ROOT))
    if (bundle/'rtl_validation/current.json').exists():
        from verify_candidate_rtl import verify as verify_candidate_rtl
        verify_candidate_rtl(bundle)
    else:
        bundle_job('verifying_candidate_rtl','verify_candidate_rtl.py',
            [relative_bundle],'bundle_rtl.log',use_tools=True)
    bundle_job('validating_six_fixture_rc','validate_fast.py',
        ['--bundle',relative_bundle,'--resume','--jobs','6'],'bundle_rc.log')
    from rc_certificate import valid
    from phy_candidate import load
    certificate=json.loads((bundle/'rc_certificate.json').read_text())
    if not valid(certificate,load(bundle,True)[1]):raise ValueError('Staged six-fixture RC certificate failed verification')
    bundle_job('running_stressed_link_diagnostic','simulate_link.py',
        ['--bundle',relative_bundle,'--fast-rc','--diagnostic','--settled-start','--dll-phase',
         '--bits','32','--process','ss','--temperature','0','--mhz','410','--duty','0.55','--skew-ps','100'],
        'bundle_link_diagnostic.log')
    capture=ROOT/'build/characterization/rx_aperture/e9ca7d2f2ae6d61b'
    while not (capture/'table.json').exists():
        state=json.loads((capture/'state.json').read_text())
        atomic(workflow,dict(status='waiting_for_rx_aperture_table',bundle=relative_bundle,observed=state['status'],qualified_phy=False))
        if state['status'] in ['complete','completed_with_failures']:
            raise RuntimeError('RX characterization ended without a complete table')
        time.sleep(10)
    bundle_job('running_full_link_matrix','regression.py',
        ['--bundle',relative_bundle,'--fast-rc','--jobs','6'],'bundle_regression.log')
    bundle_job('verifying_staged_release','check_release.py',
        ['--bundle',relative_bundle,'--stability',str(report.relative_to(ROOT)),
         '--recovery',str(recovery.relative_to(ROOT)),'--readiness',str(readiness.relative_to(ROOT)),
         '--ota-operating-points',str(operating.relative_to(ROOT))],'bundle_release.log')
    bundle_job('promoting_tested_phy','promote_phy_candidate.py',[relative_bundle],'bundle_promotion.log')
    from released_phy import current
    package,released_bundle,_=current()
    if released_bundle!=bundle:raise ValueError('Published release belongs to another candidate')
    atomic(workflow,dict(status='released',qualification=str(relative),
        stability=str(report.relative_to(ROOT)),bundle=relative_bundle,qualified_phy=True,
        package=str(package.relative_to(ROOT)),
        recovery=str(recovery.relative_to(ROOT)),readiness=str(readiness.relative_to(ROOT)),
        ota_operating_points=str(operating.relative_to(ROOT)),
        remaining=[]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout',type=Path,default=DEFAULT_LAYOUT,help='Alternate layouts must already have a passing RC audit')
    parser.add_argument('--screen',type=Path,default=DEFAULT_SCREEN,help='Architecture screen of the exact candidate source bytes')
    parser.add_argument('--pfd',type=Path,default=DEFAULT_PFD,help='Audited physical PFD matching the architecture screen')
    args=parser.parse_args();layout=args.layout.resolve()
    try:return advance(layout,args.screen.resolve(),args.pfd.resolve())
    except Exception as error:
        workflow=layout/'workflow.json'
        if workflow.exists():
            previous=json.loads(workflow.read_text());status=previous.get('status','workflow')
            if 'diagnosis' not in status:status+='_requires_diagnosis'
            atomic(workflow,dict(previous,status=status,error=str(error),qualified_phy=False))
        raise


if __name__=='__main__':main()
