#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Join the original bounded-screen owner to admitted native PVT expansion."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from continue_dll_slew_screen import owner, terminal
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'dll_slew_expansion_followup'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(screen_handoff, unit):
    if not screen_handoff.is_relative_to(ROOT / 'build/diagnostics/dll_slew_screen_followup'):
        raise ValueError('Require the original bounded-screen handoff')
    live = owner(unit)
    if (live.get('ActiveState') != 'active' or live.get('MainPID', '0') == '0' or
            not live.get('InvocationID') or 'continue_dll_slew_screen.py' not in live.get('ExecStart', '') or
            screen_handoff.name not in live['ExecStart']):
        raise ValueError('Require the live original bounded-screen owner')
    files = [screen_handoff / 'manifest.json']
    files += [ROOT / 'scripts' / n for n in (Path(__file__).name, 'continue_dll_slew_screen.py',
              'expand_dll_slew_frontends.py', 'dll_slew_coverage.py', 'dll_native_evidence.py',
              'screen_dll_slew_frontends.py', 'calibrate_dll_slew_bench.py', 'env.sh')]
    i = dict(screen_handoff=str(screen_handoff.relative_to(ROOT)), unit=unit, owner=live,
             files={str(p.relative_to(ROOT)): sha(p) for p in files}, no_outer_lease=True)
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'manifest.json', dict(identity=i, qualified_phy=False))
    return out


def completed_screen(handoff):
    r = json.loads((handoff / 'summary.json').read_text())
    prepared = json.loads((handoff / 'prepared.json').read_text())
    rel = Path(r['artifact'])
    if (not rel.is_relative_to('build/diagnostics/dll_slew_screen') or '..' in rel.parts or
            prepared.get('artifact') != str(rel) or
            prepared.get('manifest_sha256') != sha(ROOT / rel / 'manifest.json') or
            r['report_sha256'] != sha(ROOT / rel / 'summary.json')):
        raise ValueError('Bounded-screen terminal evidence changed')
    report = json.loads((ROOT / rel / 'summary.json').read_text())
    if report['ranked_survivors'] != r['ranked_survivors']:
        raise ValueError('Bounded-screen survivors changed')
    return rel, r


def run(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; stamp = sha(out / 'manifest.json')
    def unchanged():
        if (not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE) or
                out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
                sha(out / 'manifest.json') != stamp or any(sha(ROOT / n) != h for n, h in i['files'].items())):
            raise ValueError('Expansion handoff changed')
    def invoke(action, artifact, label):
        unchanged()
        p = subprocess.run(['scripts/env.sh', '--ngspice', '/usr/bin/python3',
                            'scripts/expand_dll_slew_frontends.py', action, str(artifact)],
                           cwd=ROOT, capture_output=True, text=True)
        (out / (label + '.log')).write_text(p.stdout + p.stderr)
        p.check_returncode(); unchanged(); return p.stdout
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists(): raise ValueError('Existing expansion handoff retained; no retry')
        try:
            atomic(out / 'state.json', dict(status='waiting_for_screen', qualified_phy=False))
            while not terminal(i['owner'], owner(i['unit'])):
                unchanged(); time.sleep(15)
            unchanged(); parent = ROOT / i['screen_handoff']
            rel, report = completed_screen(parent)
            if not report['ranked_survivors']:
                # No unqualified model is prepared, and no analog circuit is
                # silently selected. Preserve the evidence for the next stage.
                atomic(out / 'state.json', dict(status='held_analog_fallback_required',
                                                screen=str(rel), qualified_phy=False))
                return
            path = Path(invoke('prepare', rel, 'prepare').strip().splitlines()[-1])
            expanded = path.relative_to('/work/OpenLVDS') if path.is_relative_to('/work/OpenLVDS') else path.relative_to(ROOT)
            if not expanded.is_relative_to('build/diagnostics/dll_slew_expansion') or '..' in expanded.parts:
                raise ValueError('Unexpected expansion artifact')
            capture_manifest(out / 'prepared.json', dict(artifact=str(expanded), manifest_sha256=sha(ROOT / expanded / 'manifest.json')))
            atomic(out / 'state.json', dict(status='expanding', artifact=str(expanded), qualified_phy=False))
            invoke('run', expanded, 'run'); invoke('verify', expanded, 'verify')
            result = json.loads((ROOT / expanded / 'summary.json').read_text())
            capture_manifest(out / 'summary.json', dict(artifact=str(expanded),
                             report_sha256=sha(ROOT / expanded / 'summary.json'),
                             ranked_survivors=result['ranked_survivors'], qualified_phy=False))
            atomic(out / 'state.json', dict(status='expansion_verified' if result['ranked_survivors'] else 'held_no_survivor',
                                            ranked_survivors=result['ranked_survivors'], qualified_phy=False))
        except Exception as e:
            atomic(out / 'state.json', dict(status='held_for_diagnosis', error=str(e), qualified_phy=False))
            raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path); p.add_argument('--unit')
    a = p.parse_args()
    if a.action == 'prepare':
        if not a.unit: p.error('--unit required')
        print(prepare(a.artifact.resolve(), a.unit), flush=True)
    else: run(a.artifact.resolve())
