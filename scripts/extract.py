#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract distributed RC from the actual GDS, with simulator-facing ports.

Native PCell layouts are deliberately not used as the extraction input. Record
input hashes and resistor/capacitor counts; missing resistance is a failed run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from reduce_rc import reduce_netlist

ROOT=Path(__file__).resolve().parents[1]

def extract(design,gds,source_hash,ports=None,source_scope=None):
    digest=hashlib.sha256(gds.read_bytes()+Path(__file__).read_bytes()).hexdigest()
    out=ROOT/'build/extracted'/digest[:16]/design;out.mkdir(parents=True,exist_ok=True)
    flat=design+'_rcx'
    script=out/'extract.tcl'
    restore=''
    if ports:
        for index,(name,pin) in enumerate(ports.items(),1):
            x,y=pin['x_um'],pin['y_um']
            restore+=f'box values {x-.1:.6f}um {y-.1:.6f}um {x+.1:.6f}um {y+.1:.6f}um\nport make {index}\n'
    script.write_text(f'''drc off
crashbackups disable
locking disable
gds read {gds}
load {design}
{restore}
flatten {flat}
load {flat}
select clear
select top cell
extract style ngspice()
extract do local
extract do capacitance
extract do resistance
extract do coupling
extract do adjust
extract do unique
extract warn all
extract all
extresist simplify off
extresist all
ext2spice lvs
ext2spice merge none
ext2spice cthresh 0.01
ext2spice extresist on
ext2spice -f ngspice -o {design}.rcx.spice {flat}.ext
feedback save feedback.txt
quit -noprompt
''')
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/magic/sky130A.magicrc'
    with (out/'magic.log').open('w') as log:
        result=subprocess.run(['magic','-dnull','-noconsole','-rcfile',str(tech),str(script)],
                              cwd=out,stdout=log,stderr=subprocess.STDOUT)
    netlist=out/(design+'.rcx.spice')
    text=netlist.read_text() if netlist.exists() else ''
    text=re.sub(r'(?im)^\.subckt\s+'+re.escape(flat)+r'\b','.subckt '+design,text)
    if text:netlist.write_text(text)
    resistors=len(re.findall(r'(?im)^r\S+\s',text))
    capacitors=len(re.findall(r'(?im)^c\S+\s',text))
    match=re.search(r'(?im)^\.subckt[ \t]+'+re.escape(design)+r'[^\n]*(?:\n\+[^\n]*)*',text)
    header=match[0] if match else ''
    actual_ports=header.replace('\n+',' ').split()[2:]
    ports_ok=bool(actual_ports) and (ports is None or actual_ports==list(ports))
    passed=result.returncode==0 and ports_ok and resistors>0 and capacitors>0
    reduced=out/(design+'.reduced.spice')
    reduction=reduce_netlist(netlist,reduced) if passed else None
    final=reduced if reduction else netlist
    summary=dict(passed=passed,
        returncode=result.returncode,resistors=resistors,capacitors=capacitors,header=header,
        ports=actual_ports,ports_verified=ports_ok,reduction=reduction,
        source_sha256=source_hash,gds_sha256=hashlib.sha256(gds.read_bytes()).hexdigest(),
        source_scope_sha256=source_scope,
        netlist_sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
        netlist=str(final.relative_to(ROOT)),raw_netlist=str(netlist.relative_to(ROOT)),fingerprint=digest)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(design,json.dumps(summary),flush=True)
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--design',help='Comma-separated subset')
    p.add_argument('--digital',action='store_true')
    p.add_argument('--keep-existing',action='store_true',help='Keep unchanged, hash-verified GDS extraction results')
    a=p.parse_args()
    jobs={}
    if a.digital:
        for which,name in [('tx','openlvds_tx_core'),('rx','openlvds_ddr_rx'),('pfd','lvds_pfd')]:
            if a.design and name not in a.design.split(','):continue
            manifest=json.loads((ROOT/f'build/physical/{which}/summary.json').read_text())
            if not manifest['passed']:raise SystemExit(f'{which}: physical qualification failed')
            path=ROOT/manifest['run']/'final/gds'/f'{name}.gds'
            jobs[name]=(path,manifest['source_sha256'])
    else:
        manifest=json.loads((ROOT/'build/layout/current.json').read_text())
        for name,info in manifest['designs'].items():
            if a.design and name not in a.design.split(','):continue
            if not info.get('passed'):raise SystemExit(f'{name}: DRC/LVS failed')
            jobs[name]=(ROOT/info['gds'],manifest['source_sha256'],info['ports'],info['lvs_source_sha256'])
    results={name:extract(name,*args) for name,args in jobs.items()}
    path=ROOT/'build/extracted'/('digital.json' if a.digital else 'current.json')
    if a.keep_existing:
        previous=json.loads(path.read_text())
        for name,info in previous['designs'].items():
            if name in results:continue
            if a.digital:
                which={'openlvds_tx_core':'tx','openlvds_ddr_rx':'rx','lvds_pfd':'pfd'}[name]
                physical=json.loads((ROOT/f'build/physical/{which}/summary.json').read_text())
                gds=ROOT/physical['run']/'final/gds'/f'{name}.gds';source_hash=physical['source_sha256']
            else:
                physical=json.loads((ROOT/'build/layout/current.json').read_text())
                gds=ROOT/physical['designs'][name]['gds'];source_hash=physical['source_sha256']
            if not info['passed'] or hashlib.sha256(gds.read_bytes()).hexdigest()!=info['gds_sha256'] or (a.digital and source_hash!=info['source_sha256']):
                raise ValueError(name+': retained extraction is stale')
            if not a.digital:
                scope=physical['designs'][name]['lvs_source_sha256']
                if info.get('source_scope_sha256') not in [None,scope]:raise ValueError(name+': extracted schematic scope changed')
                info['source_scope_sha256']=scope
            if hashlib.sha256((ROOT/info['netlist']).read_bytes()).hexdigest()!=info['netlist_sha256']:
                raise ValueError(name+': retained netlist changed')
            results[name]=info
    summary=dict(passed=bool(results) and all(x['passed'] for x in results.values()),designs=results)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
