#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reprove retained routed DCC model bytes; never reuse historical timing."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import probe_dcc_native_rc_v3 as physical
import native_bank_inventory_v51 as native
from native_clock_components_v2 import definitions
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from reduce_rc import reduce_netlist
from lvs_utils import strict_setup,clean_match
import exact_rc_candidate as math

ROOT=physical.ROOT
PARENT=ROOT/'build/diagnostics/dcc_physical_recovery_v2/5b37b88a57c9d32d'
NAME=physical.NAME
VERSION='retained-routed-dcc-native-parameters-and-schur-model-proof-300-v1'
CONTEXT='retained_dcc_rc_proof_300_v1'
EXPECTED={'sky130_fd_pr__pfet_01v8_hvt':96,'sky130_fd_pr__nfet_01v8':84,
          'sky130_fd_pr__special_nfet_01v8':12,'sky130_fd_pr__res_generic_po':4}
sha=physical.sha
SCOPE='Retained routed DCC native models, geometry parameters, topology, passivity and exact RC only; no historical timing reuse, 300MHz electrical, source-matrix, loaded DLL or PHY admission'


def atomic(path,value):
    temporary=path.with_name(path.name+'.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)


def leaves(text,top):
    defs=definitions(text);result=[]
    def walk(model,pins,path,seen):
        if model in seen:raise ValueError('Recursive native DCC hierarchy')
        ports,body=defs[model]
        if set(ports)!=set(pins):raise ValueError('Invalid native DCC ports')
        def net(n):return '0' if n=='0' else pins.get(n,path+':'+n)
        for w in body:
            if w[0][0].upper() in ('R','C'):continue
            if w[0][0].upper()!='X':raise ValueError('Unknown native DCC statement')
            end=next((i for i,v in enumerate(w) if '=' in v),len(w))
            child=w[end-1];nodes=[net(n) for n in w[1:end-1]];params=dict(v.split('=',1) for v in w[end:])
            if child in defs:
                if params or len(nodes)!=len(defs[child][0]):raise ValueError('Parameterized or invalid native child')
                walk(child,dict(zip(defs[child][0],nodes)),path+':'+w[0],seen|{model})
            elif child in EXPECTED:
                count=2 if child=='sky130_fd_pr__res_generic_po' else 4
                if len(nodes)!=count:raise ValueError('Wrong native DCC primitive terminal count')
                result.append(dict(name=path+':'+w[0],nodes=nodes,model=child,params=params))
            else:raise ValueError('Unknown native DCC primitive '+child)
    walk(top,{p:p for p in defs[top][0]},top,set());return result


def parameters(expected,actual):
    if dict(Counter(d['model'] for d in expected))!=EXPECTED or dict(Counter(d['model'] for d in actual))!=EXPECTED:
        raise ValueError('Routed DCC native census changed')
    mos=native.compare_parameters([d for d in expected if 'fet_' in d['model']],
                                  [d for d in actual if 'fet_' in d['model']])
    def resistors(ds):
        result=Counter()
        for d in ds:
            if 'res_' not in d['model']:continue
            if set(d['params'])!={'w','l'}:raise ValueError('Unexpected native resistor parameters')
            result[(d['model'],native.exact_number(d['params']['w']),native.exact_number(d['params']['l']))]+=1
        return result
    if resistors(expected)!=resistors(actual):raise ValueError('Native DCC resistor dimensions changed')
    return dict(mos=mos,all_four_native_resistor_dimensions_preserved=True,native_mos=192,native_resistors=4)


def material():
    info,text,paths=physical.witnesses(PARENT)
    raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist'];reference=PARENT/'rc_audit/reference.spice'
    audit_report=json.loads((PARENT/'rc_audit.json').read_text())
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    cells=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    if sha(cells)!=audit_report['pdk_cells_sha256']:raise ValueError('Retained routed DCC PDK source changed')
    if sha(raw)!=info['reduction']['source_sha256'] or not all(audit(t)['elementwise_passive_passed'] for t in (raw.read_text(),text)):
        raise ValueError('Retained DCC raw/reduced passivity or binding failed')
    expected=leaves(reference.read_text(),NAME);actual=leaves(collapse(text),NAME)
    census=parameters(expected,actual)
    technology=[cells,pdk/'libs.tech/netgen/sky130A_setup.tcl']
    return info,paths,census,technology


def prepare():
    info,paths,census,technology=material()
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),extraction=info,census=census,
        inputs={str(p):sha(p) for p in paths},technology={str(p):sha(p) for p in technology},
        math_runtime=math.math_runtime(),scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['scope']!=SCOPE or i['parent']!=str(PARENT.relative_to(ROOT)) or m['qualified_phy'] is not False
            or any(sha(Path(n))!=h for n,h in {**i['inputs'],**i['technology']}.items())
            or math.math_runtime()!=i['math_runtime']):raise ValueError('Retained DCC model-proof context changed')
    info,_,census,_=material()
    if i['extraction']!=info or i['census']!=census:raise ValueError('Retained DCC native model changed')
    return i


def run(out):
    i=bound(out);info=i['extraction'];raw=ROOT/info['raw_netlist'];reduced=ROOT/info['netlist']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial routed DCC model proof')
        atomic(out/'state.json',dict(status='verifying',qualified_phy=False))
        try:
            target=out/'regenerated.spice';reduction=reduce_netlist(raw,target)
            if reduction!=info['reduction'] or sha(target)!=info['netlist_sha256']:raise ValueError('Routed DCC exact reduction does not regenerate')
            a=math.parse(raw.read_text());b=math.parse(reduced.read_text())
            if math.static_signature(a)!=math.static_signature(b):raise ValueError('DCC reduction changes a native model, capacitor or port')
            proof=math.witness(a,b)
            if not proof['passed']:raise ValueError('DCC independent terminal-current proof failed')
            atomic(out/'terminal_current_proof.json',proof)
            flat=out/'wire_collapsed.spice';flat.write_text(collapse(reduced.read_text()))
            setup=strict_setup(out/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
            log=out/'lvs.log';reference=PARENT/'rc_audit/reference.spice'
            p=subprocess.run(['netgen','-batch','lvs',f'{flat} {NAME}',f'{reference} {NAME}',str(setup),str(log)],cwd=out,capture_output=True,text=True)
            (out/'lvs_console.log').write_text(p.stdout+p.stderr)
            if not clean_match(log.read_text() if log.exists() else '',p.returncode):raise ValueError('Fresh routed DCC RC topology proof failed')
            bound(out)
            report=dict(extraction=info,census=i['census'],exact_reduction_regenerated=True,passivity_passed=True,
                fresh_native_topology_passed=True,independent_terminal_current_proof=proof,
                component_rc_model_proof_passed=True,historical_timing_reused=False,
                electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            report['files']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ('.execution.lock','state.json')}
            atomic(out/'summary.json',report);atomic(out/'state.json',dict(status='complete',passed=True,qualified_phy=False))
        except Exception as exc:
            atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run','campaign'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='run':
        if a.artifact is None:p.error('Supply prepared exact model-proof artifact')
        out=a.artifact.resolve()
    else:
        if a.artifact is not None:p.error('The retained physical model is fixed')
        out=prepare();print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
