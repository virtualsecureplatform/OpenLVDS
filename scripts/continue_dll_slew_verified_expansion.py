#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Join a retained direct frontend-screen owner to independently verified expansion."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'dll_slew_verified_expansion_followup'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def atomic(path, value):
    temp = path.with_name(path.name + '.tmp'); temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n'); temp.replace(path)


def capture(path, value):
    if path.exists():
        canonical = lambda v: json.dumps(v, sort_keys=True, allow_nan=False)
        if canonical(json.loads(path.read_text())) != canonical(value): raise ValueError('Verified expansion receipt changed')
    else: atomic(path, value)


def owner(unit):
    p = subprocess.run(['systemctl', '--user', 'show', unit, '-p',
                        'MainPID,InvocationID,ActiveState,SubState,Result,ExecMainStatus,LoadState,ExecStart,RemainAfterExit'],
                       capture_output=True, text=True, check=True)
    return dict(line.split('=', 1) for line in p.stdout.splitlines())


def terminal(saved, now):
    if now.get('LoadState') != 'loaded' or now.get('RemainAfterExit') != 'yes':
        raise ValueError('Retained screen owner disappeared or lost its lifetime policy')
    if now.get('InvocationID') != saved['InvocationID']: raise ValueError('Screen invocation changed')
    if now.get('MainPID', '0') != '0':
        if now['MainPID'] != saved['MainPID'] or now.get('ActiveState') != 'active':
            raise ValueError('Screen owner changed or stopped unexpectedly')
        return False
    if (now.get('ActiveState'), now.get('SubState'), now.get('Result'), now.get('ExecMainStatus')) != ('active', 'exited', 'success', '0'):
        raise ValueError('Screen owner did not finish successfully; retain partial evidence')
    return True


def prepare(screen, unit):
    if not screen.is_relative_to(ROOT / 'build/diagnostics/dll_slew_screen'):
        raise ValueError('Require the direct bounded frontend screen')
    live = owner(unit)
    if (live.get('LoadState') != 'loaded' or live.get('ActiveState') != 'active' or
            live.get('MainPID', '0') == '0' or not live.get('InvocationID') or
            live.get('RemainAfterExit') != 'yes' or 'screen_dll_slew_frontends.py' not in live.get('ExecStart', '') or
            screen.name not in live['ExecStart']):
        raise ValueError('Require the original live direct screen with RemainAfterExit=yes')
    paths = [screen / 'manifest.json', ROOT / 'requirements.json']
    paths += [ROOT / 'scripts' / n for n in (Path(__file__).name, 'screen_dll_slew_frontends.py',
               'expand_dll_slew_frontends.py', 'dll_slew_coverage.py', 'dll_native_evidence.py',
               'calibrate_dll_slew_bench.py', 'env.sh')]
    i = dict(screen=str(screen.relative_to(ROOT)), unit=unit, owner=live,
             files={str(p.relative_to(ROOT)): sha(p) for p in paths}, no_outer_lease=True)
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True); capture(out / 'manifest.json', dict(identity=i, qualified_phy=False)); return out


def run(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; stamp = sha(out / 'manifest.json')
    def unchanged():
        if (not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE) or
                out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
                sha(out / 'manifest.json') != stamp or any(sha(ROOT / n) != h for n, h in i['files'].items())):
            raise ValueError('Verified expansion handoff changed')
    def invoke(script, action, artifact, label):
        unchanged()
        p = subprocess.run(['scripts/env.sh', '--ngspice', '/usr/bin/python3', 'scripts/' + script, action, str(artifact)],
                           cwd=ROOT, capture_output=True, text=True)
        (out / (label + '.log')).write_text(p.stdout + p.stderr)
        p.check_returncode(); unchanged(); return p.stdout
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists(): raise ValueError('Existing verified handoff retained; no retry')
        try:
            atomic(out / 'state.json', dict(status='waiting_for_screen', qualified_phy=False))
            while not terminal(i['owner'], owner(i['unit'])):
                unchanged(); time.sleep(15)
            unchanged(); screen = ROOT / i['screen']
            invoke('screen_dll_slew_frontends.py', 'verify', i['screen'], 'verify_screen')
            r = json.loads((screen / 'summary.json').read_text())
            capture(out / 'screen_terminal.json', dict(artifact=i['screen'],
                      manifest_sha256=sha(screen / 'manifest.json'), report_sha256=sha(screen / 'summary.json'),
                      ranked_survivors=r['ranked_survivors'], qualified_phy=False))
            if not r['ranked_survivors']:
                atomic(out / 'state.json', dict(status='held_analog_fallback_required', qualified_phy=False)); return
            text = invoke('expand_dll_slew_frontends.py', 'prepare', i['screen'], 'prepare').strip().splitlines()[-1]
            path = Path(text)
            rel = path.relative_to('/work/OpenLVDS') if path.is_relative_to('/work/OpenLVDS') else path.relative_to(ROOT)
            if not rel.is_relative_to('build/diagnostics/dll_slew_expansion') or '..' in rel.parts:
                raise ValueError('Unexpected verified expansion artifact')
            capture(out / 'prepared.json', dict(artifact=str(rel), manifest_sha256=sha(ROOT / rel / 'manifest.json')))
            atomic(out / 'state.json', dict(status='expanding', artifact=str(rel), qualified_phy=False))
            invoke('expand_dll_slew_frontends.py', 'run', rel, 'run')
            invoke('expand_dll_slew_frontends.py', 'verify', rel, 'verify_expansion')
            result = json.loads((ROOT / rel / 'summary.json').read_text())
            capture(out / 'summary.json', dict(artifact=str(rel), report_sha256=sha(ROOT / rel / 'summary.json'),
                                              ranked_survivors=result['ranked_survivors'], qualified_phy=False))
            atomic(out / 'state.json', dict(status='expansion_verified' if result['ranked_survivors'] else 'held_no_survivor',
                                            ranked_survivors=result['ranked_survivors'], qualified_phy=False))
        except Exception as e:
            atomic(out / 'state.json', dict(status='held_for_diagnosis', error=str(e), qualified_phy=False)); raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path); p.add_argument('--unit')
    a = p.parse_args()
    if a.action == 'prepare':
        if not a.unit: p.error('--unit required')
        print(prepare(a.artifact.resolve(), a.unit), flush=True)
    else: run(a.artifact.resolve())
