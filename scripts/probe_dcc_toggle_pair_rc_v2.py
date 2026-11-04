#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Four native-RC tests of the reset-qualified five-cell DCC experiment.

Isolate matched-slew timing and actual internal terminal excursions. This
candidate is not admitted; the symmetric-combiner source pilot is separate.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import probe_dcc_native_rc_v3 as native
import probe_dcc_toggle_pair_v3 as source
from dcc_toggle_pair_physical_policy_v2 import interface_retained
from spice_library import checked_netlist
from audit_rc import collapse
from spice_dispatch import lease
from spice_engine import command,provenance
from probe_digital_dcc_v2 import sha,write,atomic

ROOT=native.ROOT
NAME='openlvds_dcc_toggle_pair_v2'
VERSION='five-cell-reset-qualified-dcc-native-rc-diagnostic-v2.1'


def witnesses(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if (i['version']!='reset-qualified-toggle-pair-physical-diagnostic-v2.1'
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())):raise ValueError('Changed physical diagnostic')
    summary=json.loads((parent/'summary.json').read_text());info=json.loads((parent/'extraction.json').read_text())
    if (not summary['physical_implementation_passed'] or not summary['rc_topology_verified']
        or not summary['signoff_same_gds'] or summary['returncode']!=0
        or json.loads((parent/'state.json').read_text())['status']!='physical_rc_complete'):
        raise ValueError('Require completed clean native physical/RC diagnostic')
    text=checked_netlist(info);run=ROOT/summary['run'];gds=run/'final/gds'/f'{NAME}.gds'
    if (sha(gds)!=info['gds_sha256'] or sha(parent/'rc_audit/reference.spice')!=info['source_scope_sha256']
        or info['source_scope_sha256']!=summary['reference_sha256']
        or collapse(text)!=(parent/'rc_audit/wire_collapsed.spice').read_text()
        or not interface_retained((run/'final/nl'/f'{NAME}.nl.v').read_text())):
        raise ValueError('Native DCC model/scope/topology mismatch')
    files=[parent/n for n in ['manifest.json','summary.json','state.json','config.json','extraction.json',
                             'rc_audit/reference.spice','rc_audit/lvs.log','rc_audit/wire_collapsed.spice']]
    files += [ROOT/n for n in i['inputs']]
    files += [gds,ROOT/info['netlist'],ROOT/info['raw_netlist'],run/'final/nl'/f'{NAME}.nl.v',run/'final/metrics.json']
    return info,text,files


def fixture(out,spec,info,text):
    deck=source.fixture(out,spec,info,text)
    deck,count=re.subn(r'(?m)^(XD[^\n]+ )'+re.escape(native.NAME)+r'$',lambda m:m[1]+NAME,deck)
    if count!=1:raise ValueError('Require one exact native DCC instance adaptation')
    return deck.replace('OpenLVDS '+native.VERSION,'OpenLVDS '+VERSION)


def prepare(parent):
    info,text,files=witnesses(parent)
    files += [Path(__file__),Path(source.__file__),Path(native.__file__),ROOT/'scripts/dcc_toggle_pair_physical_policy_v2.py',
        ROOT/'scripts/spice_library.py',ROOT/'scripts/audit_rc.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/probe_digital_dcc_v2.py']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    models=[pdk/'libs.tech/ngspice/sky130.lib.spice',*sorted((pdk/'libs.ref/sky130_fd_pr/spice').glob('*.spice'))]
    specs=[dict(variant='native',process='ss',temperature=40,mhz=410,load_ff=load,slew0_ps=100,slew180_ps=100,duty=duty)
        for load,duty in itertools.product([20,100],[.3,.7])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        pdk_files={str(p):sha(p) for p in models},simulator=provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcc_toggle_pair_rc_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'native.spice',text);tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,info,text))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,extraction=info,library_sha256=sha(out/'native.spice'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or sha(out/'native.spice')!=m['library_sha256']
        or any(sha(out/t['id']/'bench.cir')!=t['deck_sha256'] for t in m['tasks'])):
        raise ValueError('Native toggle diagnostic changed')
    checked_netlist(m['extraction']);return m


def run(out):
    m=bound(out);text=(out/'native.spice').read_text()
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native toggle diagnostic')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='dcc_toggle_pair_rc_v2_'+task['id']):
                    bound(out);process=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',process.stdout+process.stderr);process.check_returncode()
                result=source.measure(folder,task['spec'],m['extraction'],text)
                result['scope']='Native routed five-cell diagnostic only; no symmetric combiner, clocking or PHY admission'
            except Exception as exception:error=str(exception)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='native_rc_diagnostic_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    elif a.action=='run':run(out)
    else:print(json.dumps(bound(out),indent=2))
