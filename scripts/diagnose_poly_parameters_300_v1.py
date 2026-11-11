#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture evaluated PDK poly parameters in both engines, fixed TT/0 C."""
import hashlib,json,subprocess,time
from pathlib import Path
import xyce_profile_300 as xyce
import qualify_models_xyce_300_v4 as models
from native_binary_raw_v2 import validate
from xyce_raw_aliases_v148 import normalize
from spice_dispatch import lease
from qualify_dcc_xyce_300_v1 import save

ROOT=xyce.ROOT
PARAMS=['rp1','tol_poly','poly_dw','tc1rsgpu','tc2rsgpu','temper']


def main():
    identity=dict(script_sha256=xyce.sha(__file__),helper_sha256=xyce.sha(models.__file__),runtime=xyce.runtime(),qualified_models=False)
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/diagnostics/poly_parameters_300_v1'/key;out.mkdir(parents=True,exist_ok=False)
    save(out/'manifest.json',identity);rows=[]
    for engine in ['xyce','ngspice']:
        folder=out/engine;folder.mkdir()
        text=models.deck(folder,'tt',0,engine)
        nodes=['param'+str(k) for k in range(len(PARAMS))]
        text=text.replace('.tran .5p',''.join(f'BP{k} {node} 0 V={{{p}}}\n' for k,(node,p) in enumerate(zip(nodes,PARAMS)))+'.tran .5p')
        if engine=='xyce':
            text=text.replace(' V(in) ', ' '+' '.join('V('+n+')' for n in nodes)+' V(in) ')
            command=xyce.command(folder/'native.log',folder/'bench.cir')
        else:
            text=text.replace('.control\n','.save '+' '.join('V('+n+')' for n in nodes)+'\n.control\n')
            text=text.replace('run\n','run\nshow r.xrg.r0\nshowmod :resistor\n')
            rt=ROOT/'build/tools/ngspice-runtime'
            command=[str(rt/'ld-linux-x86-64.so.2'),'--library-path',str(rt),str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice'),'-n','-b','-o',str(folder/'native.log'),str(folder/'bench.cir')]
        (folder/'bench.cir').write_text(text)
        row=dict(engine=engine,command=command,complete=False,error=None)
        try:
            with lease(ROOT,priority=2,label='poly_parameters_300_v1_'+engine):
                with (folder/'console.log').open('w') as log:p=subprocess.run(command,cwd=folder,env=xyce.environment(),stdout=log,stderr=subprocess.STDOUT,timeout=90)
                if p.returncode:raise ValueError('Engine returned '+str(p.returncode))
            if engine=='xyce':normalize(folder/'bench.xyce.raw',folder/'bench.raw')
            ns,w=validate(folder/'bench.raw',{'v('+n+')' for n in nodes},6e-9)
            row.update(complete=True,parameters={p:float(w[0,ns.index('v('+n+')')]) for p,n in zip(PARAMS,nodes)},
                       outputs={n:float(w[0,ns.index('v('+n+')')]) for n in ['generic','generic_tie','generic_wide','poly']})
        except Exception as exc:row['error']=str(exc)
        row['files']={p.name:xyce.sha(p) for p in folder.iterdir() if p.is_file()};save(folder/'summary.json',row);rows.append(row)
    save(out/'summary.json',dict(rows=rows,qualified_models=False));print(out,flush=True)


if __name__=='__main__':main()
