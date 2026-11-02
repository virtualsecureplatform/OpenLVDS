#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare fresh TX isolation fixtures without an unexportable ground vector.

The first campaign's producer remains frozen while its coupled runs finish.
Use isolate_tx_convergence.py run on the returned fresh artifact. No old
simulation or result is overwritten, adopted as a pass, or retried here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import isolate_tx_convergence as original
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
sha=original.sha


def exportable(deck,tx_only):
    lines=re.findall(r'(?im)^\.print tran[^\n]+',deck)
    if len(lines)!=1:raise ValueError('Require one isolation print statement')
    tokens=lines[0].split()
    expected=1 if tx_only else 0
    if tokens.count('V(0)')!=expected:raise ValueError('Unexpected ground probe coverage')
    return deck.replace(lines[0],' '.join(t for t in tokens if t!='V(0)'))


def prepare(parent):
    baseline=original.prepare(parent)
    m=json.loads((baseline/'manifest.json').read_text());i=m['identity']
    i['inputs'][str((baseline/'manifest.json').relative_to(ROOT))]=sha(baseline/'manifest.json')
    i['code'][Path(__file__).name]=sha(Path(__file__))
    i['scope']+=' Fresh export fix excludes only the constant ground observation.'
    out=ROOT/'build/diagnostics/tx_convergence_isolation'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    tasks=[]
    for task in m['tasks']:
        old=baseline/task['id'];folder=out/task['id'];folder.mkdir(exist_ok=True)
        if any(sha(old/n)!=h for n,h in task['files'].items()):raise ValueError('Original isolation fixture changed')
        deck=(old/'bench.cir').read_text().replace(str(old)+'/library.spice',str(folder)+'/library.spice')
        deck=exportable(deck,task['id'].startswith('tx_'))
        for name,body in [('bench.cir',deck),('library.spice',(old/'library.spice').read_text())]:
            p=folder/name
            if p.exists() and p.read_text()!=body:raise ValueError('Prepared export-fix fixture changed')
            if not p.exists():p.write_text(body)
        tasks.append(dict(id=task['id'],files={n:sha(folder/n) for n in ['bench.cir','library.spice']}))
    capture_manifest(out/'manifest.json',dict(identity=i,tasks=tasks,qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);a=p.parse_args();print(prepare(a.parent.resolve()),flush=True)
