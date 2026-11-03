#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture physical PFD source only after full native frontend expansion passes."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import expand_dll_slew_frontends as expansion
import pfd_slew_policy as policy
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = expansion.sha


def gate(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics' / expansion.NAMESPACE):
        raise ValueError('Require the completed native frontend expansion')
    with (parent / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = expansion.verify(parent)
        if not report['ranked_survivors']:
            raise ValueError('No expanded standard-cell survivor; analog fallback remains required')
        winner = report['ranked_survivors'][0]
        candidates = [c for c in report['candidates'] if c['variant'] == winner and c['passed']]
        if len(candidates) != 1 or candidates[0]['worst_screened_pvt'] is None:
            raise ValueError('Winner lacks a complete worst-PVT measurement')
        m = expansion.bound(parent)
        paths = [parent / n for n in ('manifest.json', 'summary.json')]
        for t in m['tasks']:
            paths += [parent / t['id'] / n for n in (*expansion.OUTPUTS, 'summary.json')]
        return winner, candidates[0]['worst_screened_pvt'], m, paths


def prepare(parent):
    winner, worst, m, paths = gate(parent)
    baseline = ROOT / 'sky130/experiments/lvds_pfd_area_fast_reset.v'
    paths += [baseline, ROOT / 'sky130/pfd_blackboxes.v', ROOT / 'constraints/pfd.sdc',
              ROOT / 'thirdparties/OpenPLL/sky130/sky130_fd_sc_hd_pll_blackbox.v']
    inputs = dict(m['identity']['inputs'])
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    code = dict(m['identity']['code'])
    for name in (Path(__file__).name, 'pfd_slew_policy.py', 'pfd_fast_reset_policy.py', 'physical_policy.py'):
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(parent=str(parent.relative_to(ROOT)), variant=winner,
                    coverage_recipe=dict(version=expansion.coverage.VERSION, worst_screened_pvt=worst),
                    inputs=inputs, code=code, policy='pulse-area-fast-reset-slew-v1',
                    scope='Verified source-frontend winner encoded as preserved named PFD cells. Physical matching, DRC, LVS, RC, native qualification and PHY admission remain required.')
    out = ROOT / 'build/diagnostics/slew_pfd_source' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = policy.source(baseline.read_text(), winner)
        generated = {'lvds_pfd.v': source, 'slew_blackboxes.v': policy.blackboxes(winner),
                     'pfd_blackboxes.v': (ROOT / 'sky130/pfd_blackboxes.v').read_text(),
                     'pfd.sdc': (ROOT / 'constraints/pfd.sdc').read_text()}
        for name, text in generated.items(): expansion.write_once(out / name, text)
        capture_manifest(out / 'manifest.json', dict(identity=identity,
                         files={n: sha(out / n) for n in generated}, qualified_phy=False, physical_admission=False))
    return out


def bound(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (not out.is_relative_to(ROOT / 'build/diagnostics/slew_pfd_source') or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h for n, h in i['code'].items()) or
            m['qualified_phy'] is not False or m['physical_admission'] is not False or
            set(m['files']) != {'lvds_pfd.v', 'slew_blackboxes.v', 'pfd_blackboxes.v', 'pfd.sdc'} or
            any(sha(out / n) != h for n, h in m['files'].items()) or
            not policy.retained((out / 'lvds_pfd.v').read_text(), i['variant']) or
            (out / 'lvds_pfd.v').read_text() != policy.source((ROOT / 'sky130/experiments/lvds_pfd_area_fast_reset.v').read_text(), i['variant']) or
            (out / 'slew_blackboxes.v').read_text() != policy.blackboxes(i['variant']) or
            (out / 'pfd.sdc').read_bytes() != (ROOT / 'constraints/pfd.sdc').read_bytes() or
            (out / 'pfd_blackboxes.v').read_bytes() != (ROOT / 'sky130/pfd_blackboxes.v').read_bytes()):
        raise ValueError('Prepared slew PFD source changed')
    return m


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'bound']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); r = globals()[a.action](a.artifact.resolve())
    print(r if a.action == 'prepare' else json.dumps(r, indent=2), flush=True)
