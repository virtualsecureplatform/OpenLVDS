#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expand independently verified frontend survivors on the full native bench."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import dll_slew_coverage as coverage
import screen_dll_slew_frontends as screen
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'dll_slew_expansion'
sha = screen.sha
OUTPUTS = ('bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log')


def tasks(requirements, variants):
    if (not variants or len(set(variants)) != len(variants) or
            any(v not in screen.cal.CANDIDATES for v in variants)):
        raise ValueError('Expand only unique admitted bounded frontend candidates')
    result = []
    for v, spec in itertools.product(variants, coverage.source_specs(requirements)):
        p, t, f, sr, sf, o = (spec[k] for k in ('process', 'temperature', 'mhz', 'reference_slew_ps', 'feedback_slew_ps', 'offset_ps'))
        result.append(dict(id=f'{v}_{p}_{t}_{f}mhz_{sr}_{sf}_{o}ps', variant=v, spec=spec))
    return result


def survivor_gate(parent):
    with (parent / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = screen.verify(parent)
        if not report['ranked_survivors']:
            raise ValueError('No standard-cell survivor; use the approved analog fallback')
        return screen.bound(parent), report


def corner_prefix(prefix, process, temperature):
    prefix, count = re.subn(r'(?m)^(\.lib "[^"\n]+") \S+$', lambda m: m[1] + ' ' + process, prefix)
    if count != 1: raise ValueError('Require one pinned PDK corner include')
    prefix, count = re.subn(r'(?m)^\.options device temp=\S+$', f'.options device temp={temperature}', prefix)
    if count != 1: raise ValueError('Require the original temperature directive')
    return prefix


def write_once(path, text):
    if path.exists():
        if path.read_text() != text: raise ValueError('Prepared expansion changed: ' + str(path))
    else: path.write_text(text)


def prepare(parent):
    pm, report = survivor_gate(parent)
    cm = screen.cal.bound(ROOT / pm['identity']['calibration'])
    original = screen.cal.old.bound(ROOT / cm['identity']['parent'])
    q = ROOT / original['identity']['qualification']
    qm = json.loads((q / 'manifest.json').read_text())
    req_path = ROOT / 'requirements.json'; req = json.loads(req_path.read_text())
    pending = tasks(req, report['ranked_survivors'])
    inputs = dict(pm['identity']['inputs'])
    paths = [parent / n for n in ('manifest.json', 'summary.json')]
    for t in pm['tasks']:
        paths += [parent / t['id'] / n for n in (*OUTPUTS, 'summary.json')]
    paths.append(req_path)
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    code = dict(pm['identity']['code'])
    for name in (Path(__file__).name, 'dll_slew_coverage.py', 'dll_native_evidence.py'):
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(parent=str(parent.relative_to(ROOT)), variants=report['ranked_survivors'],
                    coverage_version=coverage.VERSION, inputs=inputs, code=code,
                    simulator=provenance(), pdk_source=pm['identity']['pdk_source'],
                    footprint_um2=pm['identity']['footprint_um2'], view='native',
                    scope='Source frontend with native PFD, bias and full DLL analog loading. All fifteen PVT, 390/400/410 MHz; matched and both extreme slews; 0, +/-20/50/150/300 ps. No physical, loop, reset/disable or PHY admission.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    native = (q / 'full.spice').read_text()
    pdk = Path(identity['pdk_source']['path']).read_text()
    template = (q / 'slew_ss_40_0ps_20_200/bench.cir').read_text()
    prefix = template[:template.index('XB PB NB VDDIO 0 lvds_bias')]
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        libraries = {}; networks = {}
        for v in identity['variants']:
            path = out / (v + '.spice')
            lib = native + screen.cal.conditioner(pdk, v)
            write_once(path, lib); libraries[path.name] = sha(path); networks[v] = ProbeNetwork(lib)
        prepared = []
        for t in pending:
            spec = t['spec']; f = out / t['id']; f.mkdir(exist_ok=True)
            body, aliases, stop, timing = screen.cal.old.admission.storage.native.phase_fixture(spec, qm['identity']['full_models']['observation_nodes'])
            if stop != 160 or timing != dict(start_ns=120, end_ns=160): raise ValueError('Phase fixture timing changed')
            deck = corner_prefix(prefix, spec['process'], spec['temperature']) + body
            deck += '.save i(VA) i(VD)\n.tran 5p 160n 0 20p\n.print tran ' + ' '.join('V(' + n + ')' for n in aliases.values()) + '\n.end\n'
            deck = screen.cal.old.fixture(deck, q, f, screen.cal.PORTS).replace(screen.cal.old.CELL, 'lvds_slew_conditioner')
            deck = deck.replace(f'.include "{f}/library.spice"', f'.include "{out}/{t["variant"]}.spice"')
            networks[t['variant']].validate(deck, re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0]))
            write_once(f / 'bench.cir', deck)
            prepared.append(dict(t, aliases=aliases, deck_sha256=sha(f / 'bench.cir')))
        capture_manifest(out / 'manifest.json', dict(identity=identity, libraries=libraries, tasks=prepared, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE) or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
            i['coverage_version'] != coverage.VERSION or i['view'] != 'native' or i['simulator'] != provenance() or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h for n, h in i['code'].items()) or
            sha(Path(i['pdk_source']['path'])) != i['pdk_source']['sha256'] or
            any(sha(out / n) != h for n, h in m['libraries'].items()) or
            set(m['libraries']) != {v + '.spice' for v in i['variants']} or
            [{k: v for k, v in t.items() if k not in ('aliases', 'deck_sha256')} for t in m['tasks']] != tasks(json.loads((ROOT / 'requirements.json').read_text()), i['variants']) or
            any(sha(out / t['id'] / 'bench.cir') != t['deck_sha256'] for t in m['tasks'])):
        raise ValueError('Expanded frontend experiment changed')
    return m


def aggregate(m, rows):
    candidates = []
    expected = {t['id']: t for t in m['tasks']}
    if (len(rows) != len(expected) or len({r['task'] for r in rows}) != len(rows) or
            any(r['task'] not in expected or r['spec'] != expected[r['task']]['spec'] or
                r['variant'] != expected[r['task']]['variant'] for r in rows)):
        raise ValueError('Expanded results have missing, duplicate or unexpected cases')
    for v in m['identity']['variants']:
        selected = [r for r in rows if r['variant'] == v]; checks = []; powers = []
        valid = all(r['error'] is None and r['result'] and r['result']['passed'] for r in selected)
        for p, t, mhz, pair in itertools.product(coverage.PROCESSES, coverage.TEMPERATURES, coverage.FREQUENCIES, ((100, 100), *coverage.SLEWS)):
            group = {r['spec']['offset_ps']: r['result'] for r in selected
                     if (r['spec']['process'], r['spec']['temperature'], r['spec']['mhz'],
                         (r['spec']['reference_slew_ps'], r['spec']['feedback_slew_ps'])) == (p, t, mhz, pair)}
            complete = set(group) == set(coverage.SOURCE_OFFSETS) and all(group.values())
            monotonic = balance = False; zero = None
            if complete:
                values = [group[o]['phase']['filtered_area_difference_v'] for o in coverage.SOURCE_OFFSETS]
                monotonic = bool(np.isfinite(values).all() and all(b > a for a, b in zip(values, values[1:])))
                lo = group[-20]['phase']['filtered_area_difference_v']; hi = group[20]['phase']['filtered_area_difference_v']
                balance = bool(lo < 0 < hi)
                if balance: zero = float(-20 + 40 * (-lo) / (hi - lo))
                powers.extend(g['mean_power_w'] for g in group.values())
            valid = valid and complete and monotonic and balance
            checks.append(dict(process=p, temperature=t, mhz=mhz, slew=list(pair),
                               monotonic=monotonic, zero_bracket_passed=balance, estimated_zero_offset_ps=zero))
        valid = bool(valid and powers and np.isfinite(powers).all())
        worst = max(checks, key=lambda c: abs(c['estimated_zero_offset_ps'])) if all(c['estimated_zero_offset_ps'] is not None for c in checks) else None
        candidates.append(dict(variant=v, passed=valid, checks=checks,
                               worst_screened_pvt=[worst['process'], worst['temperature']] if worst else None,
                               estimated_zero_offset_max_abs_ps=abs(worst['estimated_zero_offset_ps']) if worst else None,
                               mean_power_w=float(np.mean(powers)) if powers else None,
                               cell_area_um2=m['identity']['footprint_um2'][v]))
    eligible = [c for c in candidates if c['passed']]; rank = []
    while eligible:
        best = min(c['estimated_zero_offset_max_abs_ps'] for c in eligible)
        chosen = min((c for c in eligible if c['estimated_zero_offset_max_abs_ps'] <= best + 2),
                     key=lambda c: (c['mean_power_w'], c['cell_area_um2'], screen.cal.CANDIDATES.index(c['variant'])))
        rank.append(chosen['variant']); eligible.remove(chosen)
    return dict(candidates=candidates, ranked_survivors=rank, results=rows, qualified_phy=False,
                physical_admission=False, scope=m['identity']['scope'])


def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json')
    def unchanged(task):
        # Large parent waveforms are rehashed by bound() at campaign boundaries.
        # Dispatch checks the manifest, producer, actual model and actual deck;
        # it need not reread every unrelated parent's raw file for each case.
        if (sha(out / 'manifest.json') != stamp or
                any(sha(ROOT / 'scripts' / n) != h for n, h in m['identity']['code'].items()) or
                sha(out / (task['variant'] + '.spice')) != m['libraries'][task['variant'] + '.spice'] or
                sha(out / task['id'] / 'bench.cir') != task['deck_sha256']):
            raise ValueError('Expansion execution context changed')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists() for t in m['tasks'] for n in (*OUTPUTS, 'summary.json')):
            raise ValueError('Partial expansion retained; no retry')
        atomic(out / 'state.json', dict(status='expanding', qualified_phy=False))
        def execute(t):
            f = out / t['id']; result = error = None
            try:
                with lease(ROOT, priority=2, label='dll_slew_expand_' + t['id']):
                    unchanged(t)
                    p = subprocess.run(command(f / 'ngspice.log', f / 'bench.cir'), cwd=f, capture_output=True, text=True)
                (f / 'console.log').write_text(p.stdout + p.stderr); p.check_returncode()
                result = screen.measure(f, t)
                unchanged(t)
            except Exception as e: error = str(e)
            r = dict(task=t['id'], variant=t['variant'], spec=t['spec'], result=result, error=error,
                     manifest_sha256=stamp, files={n: sha(f / n) for n in OUTPUTS if (f / n).exists()})
            capture_manifest(f / 'summary.json', r); return r
        with ThreadPoolExecutor(max_workers=2) as pool: rows = list(pool.map(execute, m['tasks']))
        bound(out)
        if sha(out / 'manifest.json') != stamp: raise ValueError('Expansion manifest changed')
        report = dict(aggregate(m, rows), manifest_sha256=stamp)
        capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='expanded' if report['ranked_survivors'] else 'held_no_survivor', qualified_phy=False))
    return report


def verify(out):
    m = bound(out); stamp = sha(out / 'manifest.json'); rows = []
    for t in m['tasks']:
        f = out / t['id']; r = json.loads((f / 'summary.json').read_text())
        if (r['error'] is not None or r['manifest_sha256'] != stamp or set(r['files']) != set(OUTPUTS) or
                any(sha(f / n) != h for n, h in r['files'].items()) or screen.measure(f, t) != r['result']):
            raise ValueError('Expanded result changed')
        rows.append(r)
    report = dict(aggregate(m, rows), manifest_sha256=stamp)
    if report != json.loads((out / 'summary.json').read_text()): raise ValueError('Expanded aggregate changed')
    bound(out); return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run', 'verify']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); result = globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
