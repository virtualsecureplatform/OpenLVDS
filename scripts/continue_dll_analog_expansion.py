#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Terminal-only handoff from the corrected analog screen to PVT expansion."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import expand_dll_analog_frontend as expansion
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = expansion.sha


def followup(parent):
    # Check terminal scientific state, not systemd's ActiveState: a healthy
    # oneshot can remain activating/start for hours before it completes.
    if not parent.is_relative_to(ROOT / 'build/diagnostics' / expansion.screen.NAMESPACE):
        raise ValueError('Require the corrected analog source timing screen')
    state = json.loads((parent / 'state.json').read_text())
    if state['status'] not in ('analog_timing_screened', 'held_analog_timing_failed'):
        raise ValueError('Analog timing screen has not reached a terminal state')
    with (parent / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = expansion.screen.verify(parent)
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs={str((parent / n).relative_to(ROOT)): sha(parent / n)
        for n in ('manifest.json', 'summary.json', 'state.json')},
        code={n: sha(ROOT / 'scripts' / n) for n in (Path(__file__).name, 'expand_dll_analog_frontend.py')})
    out = ROOT / 'build/diagnostics/analog_expansion_followup' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
        if (out / 'state.json').exists():
            raise ValueError('Prior analog expansion handoff retained; no retry')
        if not report['ranked_survivors']:
            atomic(out / 'state.json', dict(status='held_no_analog_timing_survivor', qualified_phy=False))
            return out
        atomic(out / 'state.json', dict(status='preparing_expansion', qualified_phy=False))
        try:
            child = expansion.prepare(parent)
            atomic(out / 'state.json', dict(status='running_expansion', artifact=str(child.relative_to(ROOT)), qualified_phy=False))
            expansion.run(child)
            result = expansion.verify(child)
            if (any(sha(ROOT / n) != h for n, h in identity['inputs'].items())
                    or any(sha(ROOT / 'scripts' / n) != h for n, h in identity['code'].items())):
                raise ValueError('Analog expansion handoff inputs changed')
            capture_manifest(out / 'summary.json', dict(artifact=str(child.relative_to(ROOT)),
                summary_sha256=sha(child / 'summary.json'),
                analog_source_expansion_passed=result['analog_source_expansion_passed'], qualified_phy=False))
            atomic(out / 'state.json', dict(status='expansion_verified', artifact=str(child.relative_to(ROOT)),
                passed=result['analog_source_expansion_passed'], qualified_phy=False))
        except Exception as error:
            atomic(out / 'state.json', dict(status='held_for_diagnosis', error=str(error), qualified_phy=False))
            raise
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    print(followup(p.parse_args().artifact.resolve()), flush=True)
