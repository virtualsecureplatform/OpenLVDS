#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay a captured exact-RC bench with local analog probes; diagnostic only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from spice_engine import command, engine, provenance

ROOT=Path(__file__).resolve().parents[1]

def digest(data):return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('case',type=Path)
    p.add_argument('--hierarchy',default='XA')
    p.add_argument('--window-start-ns',type=float,default=120)
    a=p.parse_args()
    case=a.case.resolve();deck=(case/'bench.cir').read_text()
    include=re.search(r'(?im)^\.include\s+"([^"]+)"',deck)
    if not include:p.error('Captured library include missing')
    original=Path(include[1]);local=case/original.name
    source=local if local.exists() else original
    lib=source.read_bytes();text=lib.decode()
    macro=re.search(r'(?ims)^\.subckt openlvds_dll_analog\s.*?^\.ends[^\n]*',text)
    if not macro:p.error('Captured DLL macro missing')
    nodes=set()
    for line in macro[0].splitlines():
        parts=line.split()
        if not parts or not parts[0].startswith('X'):continue
        # Include terminals and local supplies of qualifier devices and follower.
        if any('__XQUAL__' in n or '__XVCOPY__' in n for n in parts[1:5]):
            for n in parts[1:5]:
                if n.startswith(('sky130','w=','l=')):break
                nodes.add(n)
    if not nodes:p.error('No extracted analog nodes found')
    probes=sorted(nodes)
    extra=' '.join(f'V({a.hierarchy}:{n})' for n in probes)
    deck=deck[:include.start(1)]+'LIBRARY_PLACEHOLDER'+deck[include.end(1):]
    deck=re.sub(r'(?im)^(\.print tran[^\n]*)',lambda m:m[1]+' '+extra,deck)
    stamp=provenance();recipe=digest(lib+deck.encode()+Path(__file__).read_bytes()+stamp.encode())[:16]
    out=ROOT/'build/diagnostics/local_analog_probes'/recipe
    out.mkdir(parents=True,exist_ok=False)
    (out/'library.spice').write_bytes(lib)
    deck=deck.replace('LIBRARY_PLACEHOLDER',str(out/'library.spice'))
    (out/'bench.cir').write_text(deck)
    (out/'producer.py').write_bytes(Path(__file__).read_bytes())
    result=dict(qualified=False,source_case=str(case),simulator=engine(),simulator_provenance=stamp,
                original_library_sha256=digest(lib),nodes=probes)
    (out/'input.json').write_text(json.dumps(result,indent=2)+'\n')
    run=subprocess.run(command(out/(engine()+'.log'),out/'bench.cir'),cwd=out,capture_output=True,text=True)
    (out/'console.log').write_text(run.stdout+run.stderr)
    result['returncode']=run.returncode
    wavefile=out/'bench.cir.prn'
    if run.returncode==0 and wavefile.exists():
        rows=[]
        for line in wavefile.read_text().splitlines():
            try:rows.append([float(x) for x in line.split()])
            except ValueError:pass
        wave=np.array(rows)
        stop=re.search(r'(?im)^\.tran\s+\S+\s+([0-9.eE+-]+)n',deck)
        complete=bool(wave.ndim==2 and len(wave)>1 and np.isfinite(wave).all() and stop and
                      wave[-1,1]>=float(stop[1])*1e-9-1e-12)
        result['complete']=complete
        if complete:
            selected=wave[wave[:,1]>=a.window_start_ns*1e-9]
            if len(selected)>1:
                result['window_start_ns']=a.window_start_ns
                result['measurements']={node:dict(min_v=float(selected[:,i].min()),
                    max_v=float(selected[:,i].max()),mean_v=float(np.sum((selected[:-1,i]+selected[1:,i])*.5*np.diff(selected[:,1]))/(selected[-1,1]-selected[0,1])))
                    for i,node in enumerate(probes,start=wave.shape[1]-len(probes))}
    result['files']={name:digest((out/name).read_bytes()) for name in
                     ['library.spice','bench.cir','producer.py']+(['bench.cir.prn'] if wavefile.exists() else [])}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),returncode=run.returncode,complete=result.get('complete',False))))
    return 0 if result.get('complete') and result.get('measurements') else 1

if __name__=='__main__':raise SystemExit(main())
