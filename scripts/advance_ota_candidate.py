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


if __name__=='__main__':main()
