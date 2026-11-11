#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete native full/reduced RC INV8 DCC timing/stress diagnostics."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import numpy as np
import xyce_profile_300 as xyce
from dcc_source_300 import model_closure
import dcc_input_waveforms_300_v2 as waveform
import dcc_source_measure_300_v2 as event_measure
from native_clock_components_v2 import definitions
from native_binary_raw_v2 import validate
from xyce_raw_aliases_v148 import normalize
from replay_bank_300_v2 import same
from spice_dispatch import lease
from qualify_dcc_xyce_300_v1 import save,specs

ROOT=xyce.ROOT
PARENT=ROOT/'build/diagnostics/dcc_inv8_physical_300_v1/c88cfb35d76fa88f'
NAME='openlvds_dcc_inv8_300'
CONTEXT='dcc_inv8_pex_300_v3'
ALIASES={'p0':'P0','p180':'P180','q':'Q','vdd':'VDD','xd.events':'XD:combine.X',
         'xd.a':'XD:first_ff.Q','xd.b':'XD:second_ff.Q','xd.areset':'XD:first_ff.RESET_B','xd.breset':'XD:second_hold.A2.t2'}


def inventory(text,ports):
    names,body=definitions(text)[NAME]
    if names!=ports:
        raise ValueError('Extracted port order changed')
    mapping=dict(VGND='0',VPWR='VDD',clock_out='Q',phase0='P0',phase180='P180',reset_n='RESET_N')
    def node(n):return mapping.get(n,'XD:'+n)
    devices=[];passive=[]
    for w in body:
        kind=w[0][0].upper()
        if kind in ['C','R']:
            continue
        if kind!='X':
            raise ValueError('Unsupported extracted statement')
        end=next((k for k,word in enumerate(w) if '=' in word),len(w))
        model=w[end-1];nodes=[node(n) for n in w[1:end-1]]
        if model=='sky130_fd_pr__res_generic_po' and len(nodes)==2:
            passive.append(dict(name='XD:'+w[0],terminals=nodes,model=model))
        elif '01v8' in model and ('nfet_' in model or 'pfet_' in model) and len(nodes)==4:
            devices.append(dict(name='XD:'+w[0],terminals=nodes,model=model,limit_v=1.95))
        else:
            raise ValueError('Unknown extracted leaf '+model)
    if not devices or not passive:
        raise ValueError('Missing native MOS or tie resistors')
    return dict(devices=devices,passive_resistors=passive)


def prepare():
    physical=json.loads((PARENT/'summary.json').read_text())
    info=json.loads((PARENT/'extraction.json').read_text())
    if not all(physical.get(n) is True for n in ['physical_checks_passed','interface_verified','native_rc_extracted','rc_topology_passed']):
        raise ValueError('Require complete physical/RC diagnostic')
    raw,reduced=ROOT/info['raw_netlist'],ROOT/info['netlist']
    if xyce.sha(raw)!=info['reduction']['source_sha256'] or xyce.sha(reduced)!=info['netlist_sha256']:
        raise ValueError('Physical RC changed')
    gds=ROOT/physical['run']/'final/gds'/f'{NAME}.gds'
    if xyce.sha(gds)!=info['gds_sha256']:
        raise ValueError('Signoff and extraction GDS differ')
    observations={kind:inventory(path.read_text(),info['ports']) for kind,path in [('full',raw),('reduced',reduced)]}
    if observations['full']!=observations['reduced']:
        raise ValueError('Reduction changed native devices or terminal endpoints')
    models=Path('/opt/pdk/ciel/sky130/versions/1689ac3f2dc763876eaf967227c7dfe831b031ae/sky130A/libs.tech/ngspice/sky130.lib.spice')
    inputs=model_closure(models)
    paths=[raw,reduced,gds,PARENT/'manifest.json',PARENT/'summary.json',PARENT/'extraction.json',PARENT/'rc_audit/lvs.log',ROOT/'clocking_300mhz.json']
    paths+=list({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    paths.append(Path(__file__).resolve())
    inputs.update({str(p):xyce.sha(p) for p in paths})
    settings=[(kind,index) for index in [0,1] for kind in ['full','reduced']]+[('reduced',2)]
    identity=dict(version=CONTEXT,inputs=inputs,runtime=xyce.runtime(),settings=settings,max_workers=2,priority=2,timeout_seconds=900,
                  historical_timing_reused=False,qualified_phy=False)
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/diagnostics'/CONTEXT/key
    out.mkdir(parents=True,exist_ok=False)
    tasks=[]
    for k,(kind,index) in enumerate(settings):
        folder=out/str(k);folder.mkdir()
        library=raw if kind=='full' else reduced
        adapted='\n'.join(line.split('$',1)[0].rstrip() for line in library.read_text().splitlines())+'\n'
        (folder/'dcc.spice').write_text(adapted)
        spec=specs()[index]
        text=f'OpenLVDS INV8 full RC diagnostic {kind}\n.lib "{models}" sf\n.include "{folder}/dcc.spice"\n'
        text+='.options device temp=40\n'+xyce.options('refined')+'VDD VDD 0 1.8\nVR RESET_N 0 PWL(0 0 1n 0 1.02n 1.8)\n'
        for phase in ['P0','P180']:
            text+='V'+phase+' '+phase+' 0 PWL(\n'+'\n'.join(f'+ {at:.17g}p {v:.17g}' for at,v in waveform.points(spec,phase))+'\n+ )\n'
        mapping=dict(VGND='0',VPWR='VDD',clock_out='Q',phase0='P0',phase180='P180',reset_n='RESET_N')
        text+='XD '+' '.join(mapping[p] for p in info['ports'])+' '+NAME+'\nCQ Q 0 20f\n'
        nodes={'P0','P180','Q','VDD','RESET_N',*ALIASES.values()}
        obs=observations[kind]
        nodes.update(n for d in obs['devices']+obs['passive_resistors'] for n in d['terminals'] if n!='0')
        stop=waveform.capture_stop_ps(spec)*1e-12
        text+=f'.tran 1p {stop:.17g} 0 1p\n.print tran format=raw precision=17 file={folder}/bench.xyce.raw '+' '.join('V('+n+')' for n in sorted(nodes))+'\n.end\n'
        (folder/'bench.cir').write_text(text)
        tasks.append(dict(id=str(k),kind=kind,spec_index=index,spec=spec,observations=obs,stop=stop,
                          deck_sha256=xyce.sha(folder/'bench.cir'),library_sha256=xyce.sha(folder/'dcc.spice')))
    save(out/'manifest.json',dict(identity=identity,tasks=tasks))
    return out


def measure(names,w,task,independent=False):
    idx={n:k for k,n in enumerate(names)}
    def get(n):return np.zeros(len(w)) if n=='0' else w[:,idx['v('+n.lower().replace(':','.')+')']]
    columns=['time',*['v('+n+')' for n in ALIASES]]
    data=np.column_stack([w[:,idx['time']],*[get(n) for n in ALIASES.values()]])
    source=event_measure.measure(columns,data,task['spec'],independent=independent)
    stress=[]
    for device in task['observations']['devices']:
        volts=[get(n) for n in device['terminals']]
        span=(max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(volts,2)) if independent
              else float(np.max(np.ptp(np.stack(volts),axis=0))))
        stress.append(dict(device=device['name'],maximum_terminal_span_v=span,passed=span<=1.95))
    return dict(source=source,native_mos=len(stress),terminal_stress=stress,native_terminal_stress_passed=all(d['passed'] for d in stress),
                diagnostic_point_passed=bool(source['source_screen_passed'] and all(d['passed'] for d in stress)),qualified_phy=False)


def bound(out):
    m=json.loads((out/'manifest.json').read_text())
    if xyce.runtime()!=m['identity']['runtime']:
        raise ValueError('Captured runtime changed')
    files={**m['identity']['inputs'],**m['identity']['runtime']['files']}
    for t in m['tasks']:
        files[str(out/t['id']/'bench.cir')]=t['deck_sha256']
        files[str(out/t['id']/'dcc.spice')]=t['library_sha256']
    for n,h in files.items():
        if xyce.sha(n)!=h:raise ValueError('Captured RC diagnostic changed: '+n)
    return m


def run(out):
    m=bound(out)
    with (out/'state.json').open('x') as f:json.dump(dict(status='running',qualified_phy=False),f)
    def one(task):
        folder=out/task['id'];row=dict(task=task,error=None,complete=False);start=time.monotonic()
        try:
            command=xyce.command(folder/'native.log',folder/'bench.cir');row['command']=command
            with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                with (folder/'console.log').open('w') as log:
                    p=subprocess.run(command,cwd=folder,env=xyce.environment(),stdout=log,stderr=subprocess.STDOUT,timeout=900)
                row['returncode']=p.returncode
                if p.returncode:raise ValueError('Xyce returned '+str(p.returncode))
            row['normalization']=normalize(folder/'bench.xyce.raw',folder/'bench.raw')
            names,w=validate(folder/'bench.raw',set(),task['stop'])
            a,b=measure(names,w,task),measure(names,w,task,True)
            if not same(a,b):raise ValueError('Independent extracted metrology differs')
            row.update(complete=True,result=a)
        except Exception as exc:row['error']=str(exc)
        row['wall_seconds']=time.monotonic()-start
        row['warnings']=xyce.warnings('\n'.join(p.read_text(errors='replace') for p in [folder/'console.log',folder/'native.log'] if p.exists()))
        row['files']={p.name:xyce.sha(p) for p in folder.iterdir() if p.is_file()}
        save(folder/'summary.json',row);return row
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,t) for t in m['tasks']]):
            rows.append(future.result());save(out/'progress.json',dict(completed=len(rows),total=5,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    bound(out);rows.sort(key=lambda r:int(r['task']['id']))
    save(out/'summary.json',dict(rows=rows,qualified_phy=False,scope='Five complete native RC INV8 diagnostics only; no 15-PVT/loaded DLL/PHY admission'))
    save(out/'state.json',dict(status='complete',cases=5,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    elif a.artifact is None:p.error('Supply artifact')
    else:run(a.artifact.resolve())
