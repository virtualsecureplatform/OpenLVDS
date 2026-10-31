#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Hand a preset experiment to native qualification after its source and RC gates."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time
from dll_campaign import atomic
from qualify_dll_candidate import CODE

ROOT = Path(__file__).resolve().parents[1]


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def ready(screen, audit):
    if screen['status'] == 'completed_with_failures':
        raise ValueError('Preset source screen failed')
    if audit is not None and not audit.get('passed'):
        raise ValueError('Preset RC audit failed')
    return screen['status'] == 'completed' and audit is not None


def run(screen, layout, pfd, source_unit, extraction_unit):
    for path in [screen,layout,pfd]:
        if not path.is_relative_to(ROOT/'build/diagnostics'):
            raise ValueError('Use isolated candidate artifacts')
    record = layout/'native_handoff.json'
    inputs = {str(p.relative_to(ROOT)):digest(p) for p in
              [screen/'manifest.json',layout/'summary.json',layout/'candidate.spice',pfd/'summary.json']}
    code = {name:digest(ROOT/'scripts'/name) for name in set(CODE)|{
        Path(__file__).name,'preset_dll_experiment.py','screen_fast_reset_dll.py'}}
    identity = dict(inputs=inputs,code=code,source_unit=source_unit,extraction_unit=extraction_unit)
    def save(status, **kw): atomic(record,dict(identity=identity,status=status,qualified_phy=False,**kw))
    def unchanged():
        if any(digest(ROOT/path)!=value for path,value in inputs.items()) or any(
                digest(ROOT/'scripts'/name)!=value for name,value in code.items()):
            raise ValueError('Captured native handoff context changed')
    def active(unit):
        result = subprocess.run(['systemctl','--user','show',unit,'-p','ActiveState','--value'],
                                capture_output=True,text=True,check=True)
        return result.stdout.strip() in ['active','activating']
    def command(label, args):
        unchanged(); save(label)
        with (layout/(label+'.log')).open('w') as log:
            result = subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','python3',
                                     'scripts/qualify_dll_candidate.py']+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        result.check_returncode()
        return layout/(label+'.log')
    with (layout/'.native_handoff.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            while True:
                unchanged(); state=json.loads((screen/'state.json').read_text())
                path=layout/'rc_audit.json'; audit=json.loads(path.read_text()) if path.exists() else None
                if ready(state,audit): break
                if state['status']!='completed' and not active(source_unit):
                    raise ValueError('Source screen process ended before passing')
                if audit is None and not active(extraction_unit):
                    raise ValueError('Extraction process ended without its RC audit')
                save('waiting_for_source_and_rc_gates',source_status=state['status'],rc_audit_present=audit is not None)
                time.sleep(10)
            log=command('prepare_native_screen',['prepare','--layout',str(layout.relative_to(ROOT)),
                '--pfd',str(pfd.relative_to(ROOT)),'--screen',str(screen.relative_to(ROOT)),'--variant','ota_w8_c4'])
            inside=Path(log.read_text().strip().splitlines()[-1])
            qualification=ROOT/inside.relative_to('/work/OpenLVDS')
            if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
                raise ValueError('Unexpected prepared qualification path')
            command('run_native_screen',['run',str(qualification.relative_to(ROOT)),'--stage','screen','--jobs','3'])
            unchanged(); save('native_screen_passed',qualification=str(qualification.relative_to(ROOT)),
                              next_gate='Measured loop model; full native qualification remains required')
        except Exception as error:
            save('held_for_diagnosis',error=str(error)); raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('screen',type=Path); p.add_argument('layout',type=Path); p.add_argument('pfd',type=Path)
    p.add_argument('--source-unit',default='openlvds-preset12-source-screen.service')
    p.add_argument('--extraction-unit',default='openlvds-preset12-extraction.service')
    a=p.parse_args();run(a.screen.resolve(),a.layout.resolve(),a.pfd.resolve(),a.source_unit,a.extraction_unit)
