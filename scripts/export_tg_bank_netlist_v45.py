#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Export the both2 physical graph with a verified balancing-tail cell."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tg_bank_physical_netlist_v45 as view
import probe_nlvt_guard2_sparse_v41 as source
import verify_tail_mim2_v40b as tail_proof
from spice_library import checked_netlist

ROOT=source.ROOT
sha=source.helper.sha
VERSION='verified-both2-physical-netlist-native-tail-export-v45.1'
CONTEXT='tg_bank_netlist_v45'
EXPECTED_COUNTS={view.INV:2,view.BUFFER:16,view.TG:20,view.FINE:31,view.TAIL:1,
                 view.SC+'buf_1':31,view.SC+'inv_1':31,view.SC+'buf_4':4,view.SC+'inv_4':12,view.SC+'and2_4':8}


def inputs(evidence,tail):
    receipt,row,parent,m=source.inherited(evidence)
    ti=json.loads((tail/'manifest.json').read_text())['identity']
    if (tail.parent!=ROOT/'build/diagnostics'/tail_proof.CONTEXT or ti['version']!=tail_proof.VERSION
            or tail.name!=hashlib.sha256(json.dumps(ti,sort_keys=True).encode()).hexdigest()[:16]
            or sha(Path(ti['cad_python']['path']))!=ti['cad_python']['sha256']):
        raise ValueError('Require unchanged independent physical balancing-tail proof')
    env=dict(os.environ)
    env['PATH']=os.pathsep.join(dict.fromkeys(str(Path(t['path']).parent) for t in ti['tools'].values()))+os.pathsep+env['PATH']
    code='import sys;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/"scripts"));import verify_tail_mim2_v40b as p;p.bound(Path(sys.argv[2]))'
    subprocess.run([ti['cad_python']['path'],'-c',code,str(ROOT),str(tail)],env=env,check=True)
    tr=json.loads((tail/'summary.json').read_text());tm=ROOT/ti['parent'];pi=tail_proof.physical.bound(tm)
    cells=(parent/'cells_both2.spice').read_text();bank=(parent/'bank_both2.spice').read_text();cap=checked_netlist(tr['extraction'])
    g=view.graph(cells,bank,cap)
    from collections import Counter
    if Counter(c['model'] for c in g['cells'])!=EXPECTED_COUNTS:raise ValueError('Physical bank component inventory changed')
    native,counts=view.native_view(cells,bank,cap,g)
    if counts['native_primitives']!=968 or counts['native_model_counts'].get(view.MIM)!=65:
        raise ValueError('Physical graph must preserve 903 MOS and 65 native MIMs')
    paths=[evidence/'summary.json',*[ROOT/n for n in receipt['identity']['inputs']]]
    paths += [parent/'manifest.json',*[parent/n for n in m['libraries']],*[ROOT/n for n in m['identity']['inputs']]]
    paths += [tail/'manifest.json',tail/'summary.json',*[ROOT/n for n in ti['inputs']],*[ROOT/n for n in pi['inputs']]]
    paths += [ROOT/tr['extraction'][k] for k in ('netlist','raw_netlist')]
    external=source.circuit.baseline.merge_files(m['identity']['pdk_files'],m['identity']['external_files'],pi['external_files'],
                                               {ti['cad_python']['path']:ti['cad_python']['sha256']})
    return g,native,counts,paths,external,str(parent.relative_to(ROOT))


def export(evidence,tail):
    g,native,counts,paths,external,parent=inputs(evidence,tail)
    yosys=shutil.which('yosys')
    if yosys is None:raise ValueError('Use --tools --ngspice with the scientific Python')
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                   if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),tail_evidence=str(tail.relative_to(ROOT)),parent=parent,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},external_files=external,
                  yosys=dict(path=yosys,sha256=sha(Path(yosys))),graph=g,native_counts=counts,qualified_phy=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    source.helper.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    source.helper.write(out/'bank.v',view.verilog(g));source.helper.write(out/'cells.v',view.blackboxes(g))
    source.helper.write(out/'bank.sch.spice',native)
    source.helper.write(out/'check.ys',f'read_verilog -lib cells.v\nread_verilog bank.v\nhierarchy -check -top {view.NAME}\nwrite_json bank.json\n')
    p=subprocess.run([yosys,'-s','check.ys'],cwd=out,capture_output=True,text=True)
    source.helper.write(out/'yosys.log',p.stdout+p.stderr);p.check_returncode()
    result=view.verify_json(json.loads((out/'bank.json').read_text()),g)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()) or any(sha(Path(n))!=h for n,h in external.items()):
        raise ValueError('Physical graph export input closure changed')
    report=dict(result=result,native_counts=counts,qualified_phy=False,electrical_qualification_passed=False,
                routed_geometry_qualified=False,tail_cell_rc_applied_to_native_reference=False)
    report['files']={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    source.helper.atomic(out/'summary.json',report)
    bound(out);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['qualified_phy'] or r['qualified_phy'] or r['electrical_qualification_passed']
            or r['routed_geometry_qualified'] or r['tail_cell_rc_applied_to_native_reference']
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(Path(n))!=h for n,h in i['external_files'].items())
            or any(sha(out/n)!=h for n,h in r['files'].items())
            or sha(Path(i['yosys']['path']))!=i['yosys']['sha256']
            or view.verify_json(json.loads((out/'bank.json').read_text()),i['graph'])!=r['result']
            or r['native_counts']!=i['native_counts']):
        raise ValueError('Physical bank graph export changed')
    return i


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('evidence',type=Path);p.add_argument('--tail-evidence',type=Path,required=True)
    a=p.parse_args();print(export(a.evidence.resolve(),a.tail_evidence.resolve()),flush=True)
