#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate a larger transient Newton iteration budget after a terminal timestep collapse."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,Result,ExecStart'],capture_output=True,text=True,check=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def deck_with_budget(text,parent,out):
    tran=re.findall(r'(?im)^\.tran[^\n]*$',text)
    if len(tran)!=1 or tran[0].split()[1:]!=['20p','188.049n','0','1p'] or re.search(r'\bitl4\s*=',text,re.I):
        raise ValueError('Require the original 188.049 ns/1 ps diagnostic without an existing iteration override')
    container=lambda p:Path('/work/OpenLVDS')/p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
    aliases={f'.include "{p}/library.spice"' for p in [parent,container(parent)]}
    found=[line for line in aliases if text.count(line)]
    if len(found)!=1 or text.count(found[0])!=1:raise ValueError('Ambiguous diagnostic library inclusion')
    text=text.replace(found[0],f'.include "{container(out)}/library.spice"')
    first,rest=text.split('\n',1)
    return first+'\n.options itl4=100\n'+rest


def prepare(parent,unit):
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_feedback_link_diagnostic'):
        raise ValueError('Use the separate interoperability diagnostic namespace')
    terminal=owner(unit)
    if terminal.get('MainPID')!='0' or terminal.get('ActiveState')!='failed' or terminal.get('Result')!='exit-code':
        raise ValueError('Require the terminal failed owner, never a live or timed-out observation')
    command=terminal.get('ExecStart','')
    if 'scripts/probe_corrected_driver_tia_diagnostic.py run ' not in command or not re.search(re.escape(str(parent.relative_to(ROOT)))+r'(?=\s|;|$)',command):
        raise ValueError('Terminal owner belongs to another diagnostic context')
    if (parent/'summary.json').exists():raise ValueError('Retain completed diagnostic evidence')
    log=(parent/'ngspice.log').read_text()
    failure=re.search(r'Timestep too small; time = ([^,]+), timestep = ([^:]+): trouble with node "([^"]+)"',log)
    if not failure:raise ValueError('Require a recorded terminal transient timestep collapse')
    m=json.loads((parent/'manifest.json').read_text());i=deepcopy(m['identity'])
    if i.get('diagnostic_only') is not True or i.get('maximum_step_ps')!=1 or 'newton_budget' in i:
        raise ValueError('Require the original one-ps exploratory diagnostic, without repeated numerical retries')
    for path,h in i['inputs'].items():
        if sha(ROOT/path)!=h:raise ValueError('Diagnostic source evidence changed')
    for name,h in i['code'].items():
        if sha(ROOT/'scripts'/name)!=h:raise ValueError('Diagnostic producer changed')
    for name,h in m['files'].items():
        if sha(parent/name)!=h:raise ValueError('Failed diagnostic inputs changed')
    paths=[parent/n for n in ['manifest.json','bench.cir','library.spice','bench.raw','ngspice.log','console.log']]
    i['inputs'].update({str(p.relative_to(ROOT)):sha(p) for p in paths});i['code'][NAME]=sha(Path(__file__))
    i['newton_budget']=dict(itl4=100,parent=str(parent.relative_to(ROOT)),unit=unit,terminal_owner=terminal,
        failure_time_s=float(failure[1]),failure_timestep_s=float(failure[2]),failure_node=failure[3],
        scope='Single controlled numerical intervention after a terminal failure. Increase transient Newton iteration capacity only. Same topology, fixed supplies, initial conditions, stimuli, duration, 1 ps maximum step and all accuracy tolerances. Original partial output is retained; no automatic retry chain or electrical admission.')
    out=ROOT/'build/diagnostics/receiver_feedback_link_diagnostic'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    text=deck_with_budget((parent/'bench.cir').read_text(),parent,out)
    for name,body in [('bench.cir',text),('library.spice',(parent/'library.spice').read_text())]:
        p=out/name
        if p.exists() and p.read_text()!=body:raise ValueError('Prepared Newton-budget context changed')
        if not p.exists():p.write_text(body)
    capture_manifest(out/'manifest.json',dict(identity=i,qualified_phy=False,files={n:sha(out/n) for n in ['bench.cir','library.spice']}))
    return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_feedback_link_diagnostic'):
        raise ValueError('Use a prepared numerical diagnostic')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];policy=i['newton_budget'];parent=ROOT/policy['parent']
    if (policy.get('itl4')!=100 or sha(Path(__file__))!=i['code'].get(NAME) or
            (out/'library.spice').read_bytes()!=(parent/'library.spice').read_bytes() or
            (out/'bench.cir').read_text()!=deck_with_budget((parent/'bench.cir').read_text(),parent,out)):
        raise ValueError('Numerical diagnostic changed topology, fixture or declared iteration budget')
    import probe_corrected_driver_tia_diagnostic as original
    return original.run(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('parent',type=Path);a.add_argument('--producer-unit',required=True)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.parent.resolve(),a.producer_unit),flush=True)
    else:print(run(a.artifact.resolve()),flush=True)
