#!/usr/bin/env python3
"""Join an exact live calibration owner to bounded frontend screening."""
import argparse,fcntl,hashlib,json,subprocess,time
from pathlib import Path
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'-p','MainPID,InvocationID,ActiveState,Result,ExecMainStatus,LoadState,ExecStart'],check=True,capture_output=True,text=True)
    return dict(x.split('=',1) for x in p.stdout.splitlines())

def terminal(saved,now):
    if now.get('LoadState')!='loaded':raise ValueError('Calibration service disappeared')
    if now.get('MainPID','0')!='0':
        if (now['MainPID'],now['InvocationID'])!=(saved['MainPID'],saved['InvocationID']):raise ValueError('Calibration owner changed')
        return False
    if now.get('InvocationID') not in ['',saved['InvocationID']]:raise ValueError('Calibration invocation changed')
    if now.get('Result')!='success' or now.get('ExecMainStatus')!='0':raise ValueError('Calibration owner failed; retain partial output')
    return True

def prepare(calibration,unit):
    if not calibration.is_relative_to(ROOT/'build/diagnostics/dll_slew_bench'):raise ValueError('Use isolated calibration')
    live=owner(unit)
    if live.get('ActiveState')!='active' or live.get('MainPID','0')=='0' or not live.get('InvocationID'):
        raise ValueError('Require live original calibration owner')
    if 'calibrate_dll_slew_bench.py' not in live.get('ExecStart','') or calibration.name not in live['ExecStart']:
        raise ValueError('Calibration command differs')
    files=[calibration/'manifest.json']+[ROOT/'scripts'/n for n in [Path(__file__).name,'screen_dll_slew_frontends.py','calibrate_dll_slew_bench.py','env.sh']]
    i=dict(calibration=str(calibration.relative_to(ROOT)),unit=unit,owner=live,files={str(p.relative_to(ROOT)):sha(p) for p in files},no_outer_lease=True)
    out=ROOT/'build/diagnostics/dll_slew_screen_followup'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);capture_manifest(out/'manifest.json',dict(identity=i,qualified_phy=False));return out

def run(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (not out.is_relative_to(ROOT/'build/diagnostics/dll_slew_screen_followup') or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or sha(out/'manifest.json')!=stamp or
            any(sha(ROOT/n)!=h for n,h in i['files'].items())):raise ValueError('Screen handoff changed')
    def invoke(action,artifact,label):
        unchanged();p=subprocess.run(['scripts/env.sh','--ngspice','/usr/bin/python3','scripts/screen_dll_slew_frontends.py',action,artifact],cwd=ROOT,capture_output=True,text=True)
        (out/(label+'.log')).write_text(p.stdout+p.stderr);p.check_returncode();unchanged();return p.stdout
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Existing handoff retained; no retry')
        try:
            atomic(out/'state.json',dict(status='waiting_for_calibration',qualified_phy=False))
            while not terminal(i['owner'],owner(i['unit'])):unchanged();time.sleep(15)
            unchanged()
            if not (ROOT/i['calibration']/'summary.json').is_file():raise ValueError('Calibration ended without terminal report')
            text=invoke('prepare',i['calibration'],'prepare').strip().splitlines()[-1]
            path=Path(text)
            rel=path.relative_to('/work/OpenLVDS') if path.is_relative_to('/work/OpenLVDS') else path.relative_to(ROOT)
            if not rel.is_relative_to('build/diagnostics/dll_slew_screen'):raise ValueError('Unexpected screen artifact')
            capture_manifest(out/'prepared.json',dict(artifact=str(rel),manifest_sha256=sha(ROOT/rel/'manifest.json')))
            atomic(out/'state.json',dict(status='screening',artifact=str(rel),qualified_phy=False))
            invoke('run',str(rel),'run');invoke('verify',str(rel),'verify')
            report=json.loads((ROOT/rel/'summary.json').read_text())
            capture_manifest(out/'summary.json',dict(artifact=str(rel),report_sha256=sha(ROOT/rel/'summary.json'),ranked_survivors=report['ranked_survivors'],qualified_phy=False))
            atomic(out/'state.json',dict(status='screen_verified' if report['ranked_survivors'] else 'held_no_survivor',ranked_survivors=report['ranked_survivors'],qualified_phy=False))
        except Exception as e:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(e),qualified_phy=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--unit');a=p.parse_args()
    if a.action=='prepare':
        if not a.unit:p.error('--unit required')
        print(prepare(a.artifact.resolve(),a.unit),flush=True)
    else:run(a.artifact.resolve())
