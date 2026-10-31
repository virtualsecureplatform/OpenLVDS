#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare and register W8/C4 screening only after its extraction and audit pass."""
import json
import os
from pathlib import Path
import subprocess
import time
from dll_campaign import atomic

ROOT=Path(__file__).resolve().parents[1]
LAYOUT=ROOT/'build/diagnostics/dll_layout/c465a14562c2ff4f'


def main():
    os.environ['OPENLVDS_SPICE']='ngspice'
    while not (LAYOUT/'rc_audit.json').exists():
        state=subprocess.run(['systemctl','--user','is-active','openlvds-w8c4-rc.service'],capture_output=True,text=True)
        if state.stdout.strip() in ['failed','inactive']:
            raise RuntimeError('Extraction ended without an audit; inspect systemd journal')
        time.sleep(10)
    if not json.loads((LAYOUT/'rc_audit.json').read_text())['passed']:
        raise RuntimeError('W8/C4 RC connectivity audit failed')
    command=['scripts/env.sh','--ngspice','python3','scripts/qualify_dll_candidate.py','prepare',
        '--layout',str(LAYOUT.relative_to(ROOT)),'--pfd','build/diagnostics/pfd_area_physical',
        '--screen','build/diagnostics/dll_architecture/6d99d42cf3eb5d31','--variant','ota_w8_c4']
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    (LAYOUT/'qualification_prepare.log').write_text(result.stdout+result.stderr)
    result.check_returncode()
    inside=Path(result.stdout.strip().splitlines()[-1]);relative=inside.relative_to('/work/OpenLVDS')
    artifact=ROOT/relative
    if not (artifact/'manifest.json').is_file():raise ValueError('Prepared manifest missing')
    config=ROOT/'build/diagnostics/resident_jobs/config.json'
    old=json.loads(config.read_text()) if config.exists() else {}
    old.update(disabled=['qualify_cp'],ota_qualification=str(relative))
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
    wait_for(['screen_passed'])
    def model(all_pvt=False):
        args=['scripts/env.sh','--ngspice','python3','scripts/measure_dll_stability.py',str(relative)]
        if all_pvt:args+=['--all-pvt']
        result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
        (LAYOUT/('stability_all.log' if all_pvt else 'stability_screen.log')).write_text(result.stdout+result.stderr)
        result.check_returncode()
        report=ROOT/Path(result.stdout.strip().splitlines()[-1]).relative_to('/work/OpenLVDS')
        if not json.loads(report.read_text())['passed']:
            atomic(workflow,dict(status='stability_requires_diagnosis',report=str(report.relative_to(ROOT))))
            raise RuntimeError('Measured stability or model validation failed')
        from stability_evidence import verified
        inputs=json.loads((artifact/'manifest.json').read_text())['identity']['full_models']['inputs']
        corners=('ss_0','tt_25','ff_0')
        if all_pvt:
            req=json.loads((artifact/'requirements.json').read_text());corners=tuple(f'{p}_{t}' for p in req['process_corners'] for t in req['temperatures_c'])
        verified(report,inputs,corners)
        return report
    report=model()
    old=json.loads(config.read_text());old.update(ota_stage='full',ota_stability=str(report.relative_to(ROOT)))
    atomic(config,old)
    wait_for(['completed'])
    report=model(True)
    result=subprocess.run(['scripts/env.sh','--ngspice','python3','scripts/stage_phy_candidate.py',str(relative)],
        cwd=ROOT,capture_output=True,text=True)
    (LAYOUT/'bundle_prepare.log').write_text(result.stdout+result.stderr);result.check_returncode()
    bundle=ROOT/Path(result.stdout.strip().splitlines()[-1]).relative_to('/work/OpenLVDS')
    if not (bundle/'manifest.json').is_file():raise ValueError('Staged PHY manifest missing')
    def bundle_job(status,script,args,log):
        atomic(workflow,dict(status=status,qualification=str(relative),bundle=str(bundle.relative_to(ROOT)),qualified_phy=False))
        result=subprocess.run(['scripts/env.sh','--ngspice','python3','scripts/'+script]+args,
            cwd=ROOT,capture_output=True,text=True)
        (LAYOUT/log).write_text(result.stdout+result.stderr)
        if result.returncode:
            atomic(workflow,dict(status=status+'_requires_diagnosis',bundle=str(bundle.relative_to(ROOT)),log=str((LAYOUT/log).relative_to(ROOT)),qualified_phy=False))
            result.check_returncode()
        return result
    relative_bundle=str(bundle.relative_to(ROOT))
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
    atomic(workflow,dict(status='link_matrix_complete_remaining_signoff',qualification=str(relative),
        stability=str(report.relative_to(ROOT)),bundle=relative_bundle,qualified_phy=False,
        remaining=['actual_operating_range_ota_characterization','native_readiness_replay',
                   'worst_model_corner_recovery','release_checker_and_exact_byte_promotion']))


if __name__=='__main__':main()
