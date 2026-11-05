#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare complete actual joint/component native stage delays and wire loads."""
import argparse
import hashlib
import json
import re
import shlex
from pathlib import Path
from collections import defaultdict
import numpy as np
import probe_joint_bank_zero_v53 as p
import verify_joint_bank_zero_v54 as verified
import probe_nlvt_guard2_bank_v36 as old
from joint_bank_observations_v53 import Union,instances
from native_clock_components_v2 import definitions
from reduce_rc import number

ROOT=p.ROOT
VERSION='complete-joint-versus-component-bank-stage-and-capacitance-diagnosis-v55.1'
CONTEXT='joint_bank_zero_diagnosis_v55'


def diagnose(evidence,component_parent):
    vi=verified.bound(evidence);vm=json.loads((evidence/'summary.json').read_text())
    if not vm['full_native_waveform_remeasured']:raise ValueError('Require complete independent waveform evidence')
    om=old.bound(component_parent);task=next(t for t in om['tasks'] if t['spec']['profile']=='both2')
    row=json.loads((component_parent/task['id']/'summary.json').read_text())
    if row['error'] is not None or any(p.sha(component_parent/task['id']/n)!=h for n,h in row['files'].items()):
        raise ValueError('Complete component reference changed')
    paths=[evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in vi['inputs']],Path(__file__),Path(verified.__file__),
           component_parent/'manifest.json',component_parent/task['id']/'summary.json',
           *[component_parent/task['id']/n for n in row['files']],*[ROOT/n for n in om['identity']['inputs']],
           component_parent/'cells_both2.spice',component_parent/'bank_both2.spice']
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),component_reference=str(component_parent.relative_to(ROOT)),
                  inputs={str(path.relative_to(ROOT)):p.sha(path) for path in paths})
    dest=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if dest.exists():bound(dest);return dest
    dest.mkdir(parents=True);p.baseline.atomic(dest/'manifest.json',dict(identity=identity,qualified_phy=False))
    out=p.ROOT/vi['parent'];i=p.bound(out)['identity'];record=p.evidence(p.ROOT/i['parent']);pi=record['placement'];physical=p.ROOT/record['identity']['parent'];info=record['identity']['extraction'];folder=(p.ROOT/info['raw_netlist']).parent
    u=Union();seen=set();ext=(folder/(i['top']+'_rcx.ext')).read_text()
    for line in ext.splitlines():
     if not line.startswith(('node ','equiv ','port ')):continue
     w=shlex.split(line);seen.add(w[1]);u.find(w[1])
     if w[0]=='equiv':seen.add(w[2]);u.join(w[1],w[2])
    body=definitions((p.ROOT/info['netlist']).read_text())[i['top']][1];vertices=set()
    for w in body:
     if w[0][0].upper()=='R':u.join(w[1],w[2]);vertices.update(w[1:3])
     elif w[0][0].upper()=='X':
      end=next((j for j,v in enumerate(w) if '=' in v),len(w));vertices.update(w[1:end-1])
    for n in vertices:
     base=re.sub(r'\.t\d+$','',n)
     if base in seen:u.join(n,base)
    ids=instances((physical/'native'/(i['top']+'.mag')).read_text(),pi['plan']);labels={}
    for c in pi['graph']['cells']:
     for pin,net in c['pins'].items():
      alias=ids[c['name']]+'.'+pin
      if alias in seen:
       key=u.find(alias)
       assert labels.get(key,net)==net;labels[key]=net
    canon=lambda n:labels.get(u.find(n))
    names,w=p.validate(out/'0/bench.raw',{'v(in)','v(out)'},20e-9);idx={n:j for j,n in enumerate(names)};t=w[:,idx['time']]*1e12;window=(t>=10000)&(t<=20000);tw=t[window]
    def data(n):return w[:,idx['v('+n.replace(':','.').lower()+')']][window]
    input={k:p.baseline.crossings(tw,data('IN'),up)[0] for k,up in [('rise',True),('fall',False)]}
    stages=defaultdict(set)
    for d in i['observations']['devices']:
     ns=d['terminals'];raw=lambda n:n[3:] if n.startswith('XD:') else 'VPWR' if n=='VDD' else 'VGND' if n=='0' else n
     labs=[canon(raw(n)) for n in ns]
     if labs[1]=='IN':
      stages['input_gate'].add(ns[1]);stages['input_inverse_output'].update(ns[k] for k in (0,2) if labs[k]=='tap0')
     if labs[1]=='selected':
      stages['fine_inverse_gate'].add(ns[1]);stages['fine_inverse_output'].update(ns[k] for k in (0,2) if labs[k]=='OUT')
     if {labs[0],labs[2]}=={'tap0','tree0_0'}:
      stages['first_tg_input'].update(ns[k] for k in (0,2) if labs[k]=='tap0');stages['first_tg_output'].update(ns[k] for k in (0,2) if labs[k]=='tree0_0')
     if {labs[0],labs[2]}=={'tree0_0','selected'}:
      stages['root_tg_input'].update(ns[k] for k in (0,2) if labs[k]=='tree0_0');stages['root_tg_output'].update(ns[k] for k in (0,2) if labs[k]=='selected')
    stages['OUT']={'OUT'};bands={}
    for stage,nodes in stages.items():
     rows=[]
     for n in nodes:
      v=data(n);row={'node':n}
      for label,up in [('rise',True),('fall',False)]:
       direction=up if stage in ('input_gate','fine_inverse_output','OUT') else not up
       times=p.baseline.crossings(tw,v,direction)
       assert len(times)==1,(stage,n,times);row[label+'_delay_ps']=float(times[0]-input[label])
      rows.append(row)
     bands[stage]={'nodes':len(rows),'rise_delay_ps':[min(r['rise_delay_ps'] for r in rows),max(r['rise_delay_ps'] for r in rows)],'fall_delay_ps':[min(r['fall_delay_ps'] for r in rows),max(r['fall_delay_ps'] for r in rows)]}
    newcap=defaultdict(float)
    for x in body:
     if x[0][0].upper()!='C':continue
     a,b=map(canon,x[1:3])
     if a!=b:
      for n in (a,b):
       if n:newcap[n]+=number(x[3])*1e15
    # Flatten the measured component-RC reference with all top-level nets named.
    ref=component_parent
    defs=definitions((ref/'cells_both2.spice').read_text()+(ref/'bank_both2.spice').read_text());root='openlvds_dcdl_c16_f32_both2_v36';flat=[];r=Union()
    def walk(model,mapping,path):
     ports,statements=defs[model]
     node=lambda n:n if n=='0' else mapping.get(n,path+':'+n)
     for x in statements:
      if x[0][0].upper() in ('R','C'):flat.append((x[0][0].upper(),node(x[1]),node(x[2]),number(x[3])))
      elif x[0][0].upper()=='X':
       end=next((j for j,v in enumerate(x) if '=' in v),len(x));child=x[end-1];nodes=[node(n) for n in x[1:end-1]]
       if child in defs:walk(child,dict(zip(defs[child][0],nodes)),path+':'+x[0])
    topnets={n for x in defs[root][1] for n in x[1:next((j for j,v in enumerate(x) if '=' in v),len(x))-1]}
    walk(root,{n:n for n in topnets},'REF')
    for kind,a,b,v in flat:
     if kind=='R':r.join(a,b)
    oldlabel={r.find(n):n for n in topnets};oldcap=defaultdict(float)
    for kind,a,b,v in flat:
     if kind!='C':continue
     a=oldlabel.get(r.find(a));b=oldlabel.get(r.find(b))
     if a!=b:
      for n in (a,b):
       if n:oldcap[n]+=v*1e15
    caps={n:{'component_ff':oldcap[n],'joint_ff':newcap[n],'added_ff':newcap[n]-oldcap[n]} for n in ('IN','tap0','tree0_0','selected','OUT')}
    result=dict(bands=bands,explicit_capacitance=caps,scope='Complete trace and linear wire capacitance diagnosis only; native nonlinear capacitance excluded; no timing admission')

    # Compare the same measured native stages against the complete both2 trace.
    oldm=old.bound(ref);oldspec=next((task for task in oldm['tasks'] if task['spec']['profile']=='both2'))
    oldfolder=ref/oldspec['id'];olddevices=oldm['identity']['devices']['both2']
    names0,w0=p.validate(oldfolder/'bench.raw',{'v(in)','v(out)'},20e-9);idx0={n:j for j,n in enumerate(names0)};t0=w0[:,idx0['time']]*1e12;sel0=(t0>=10000)&(t0<=20000);tt0=t0[sel0]
    def datum0(n):return w0[:,idx0['v('+n.replace(':','.').lower()+')']][sel0]
    def canon0(n):
     n='VPWR' if n=='VDD' else 'VGND' if n=='0' else n
     if n.startswith('XD:'):
      n=n[3:]
      if n not in topnets:n='REF:'+n
     return oldlabel.get(r.find(n))
    ss=defaultdict(set)
    for d in olddevices:
     ns=d['terminals'];ls=[canon0(n) for n in ns]
     if ls[1]=='IN':ss['input_gate'].add(ns[1]);ss['input_inverse_output'].update(ns[k] for k in (0,2) if ls[k]=='tap0')
     if ls[1]=='selected':ss['fine_inverse_gate'].add(ns[1]);ss['fine_inverse_output'].update(ns[k] for k in (0,2) if ls[k]=='OUT')
     if {ls[0],ls[2]}=={'tap0','tree0_0'}:ss['first_tg_input'].update(ns[k] for k in (0,2) if ls[k]=='tap0');ss['first_tg_output'].update(ns[k] for k in (0,2) if ls[k]=='tree0_0')
     if {ls[0],ls[2]}=={'tree0_0','selected'}:ss['root_tg_input'].update(ns[k] for k in (0,2) if ls[k]=='tree0_0');ss['root_tg_output'].update(ns[k] for k in (0,2) if ls[k]=='selected')
    ss['OUT']={'OUT'};oldbands={};aa={k:p.baseline.crossings(tt0,datum0('IN'),up)[0] for k,up in [('rise',True),('fall',False)]}
    for stage,nodes in ss.items():
     bb={}
     for label,up in [('rise',True),('fall',False)]:
      direction=up if stage in ('input_gate','fine_inverse_output','OUT') else not up
      dd=[float(p.baseline.crossings(tt0,datum0(n),direction)[0]-aa[label]) for n in nodes]
      bb[label+'_delay_ps']=[min(dd),max(dd)]
     bb['nodes']=len(nodes);oldbands[stage]=bb
    result['component_stage_bands']=oldbands


    verified.bound(evidence);old.bound(component_parent)
    if any(p.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Diagnosis inputs changed')
    result.update(qualified_phy=False,electrical_qualification_passed=False,complete_trace_diagnosis_passed=True)
    p.baseline.atomic(dest/'summary.json',result);bound(dest);return dest


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(p.sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or not r['complete_trace_diagnosis_passed'] or r['qualified_phy'] or r['electrical_qualification_passed']):
        raise ValueError('Complete native diagnosis context changed')
    return i


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('evidence',type=Path);parser.add_argument('--component-reference',type=Path,required=True)
    a=parser.parse_args();print(diagnose(a.evidence.resolve(),a.component_reference.resolve()),flush=True)
