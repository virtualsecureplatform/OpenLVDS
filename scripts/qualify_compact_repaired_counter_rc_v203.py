#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh distributed RC of the compact same-logic repaired counter GDS."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import build_compact_repaired_counter_v210 as physical
import extract_native_flat_v4 as extractor
import native_bank_inventory_v51 as inventory
import exact_rc_candidate as exact
from probe_digital_dcc_v2 import atomic

ROOT=physical.ROOT
NAME=physical.NAME
VERSION='compact-same-logic-21-macro-clock-counter-full-native-rc-v203.1'
CONTEXT='compact_repaired_counter_rc_v203'
EXPECTED={'sky130_fd_pr__nfet_01v8':223,'sky130_fd_pr__pfet_01v8_hvt':223,'sky130_fd_pr__cap_mim_m3_1':48}
SCOPE='Exact compact repaired 21-macro counter/clock-driver GDS distributed RC, unchanged native models/parameters/topology, passive reduction and independent current witnesses only; no counter timing/all-PVT/DCC/PHY admission'


def sha(path):
    # Same complete-byte SHA-256, bounded memory for large retained waveforms.
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def census(text):
    ports,devices=inventory.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',text),NAME+'_flat')
    counts=dict(Counter(d['model'] for d in devices))
    if ports!=physical.PORTS or counts!=EXPECTED or len(devices)!=494:raise ValueError('Repaired counter native inventory or public port order changed')
    return dict(ports=ports,native_model_counts=counts,native_primitives=len(devices))


def require_physical(state,result):
    if state!=dict(status='complete',passed=True,qualified_phy=False) or result.get('compact_counter_physical_passed') is not True or result.get('same_native_logic') is not True:raise ValueError('Require complete passing compact same-logic counter')
    p=result['physical']
    if p.get('passed') is not True or p.get('drc_count')!='0' or p.get('lvs_passed') is not True or p.get('macro_count')!=21:raise ValueError('Compact counter physical geometry failed')
    for key in ('all_shared_native_masters_identical','all_integrated_native_masters_preserved','integrated_macro_placements_verified'):
        if p['native_master_witness'].get(key) is not True:raise ValueError('Compact counter native master or placement witness failed')


def certification_inputs():
    code="""import sys,json
from pathlib import Path
sys.path.insert(0,'scripts');import build_parallel_output_cell_v111 as p
paths=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})
print(json.dumps(dict(files=[str(f.relative_to(p.ROOT)) for f in paths],math_runtime=p.math_proof.math_proof()['runtime'])))
"""
    p=subprocess.run([physical.original.repaired.CAD,'-c',code],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:raise ValueError('Counter RC certification environment refused:\n'+p.stderr[-2000:])
    result=json.loads(p.stdout)
    if result['math_runtime']!=exact.math_runtime():raise ValueError('Counter RC independent math runtime changed')
    return [ROOT/n for n in result['files']]


def prepare(parent):
    m=physical.bound(parent);i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    require_physical(json.loads((parent/'state.json').read_text()),r)
    if any(sha(parent/n)!=h for n,h in r['files'].items()):raise ValueError('Qualified counter physical outputs changed')
    folder=parent/NAME;native=census((folder/(NAME+'.lvs.spice')).read_text())
    if sha(folder/(NAME+'.gds'))!=r['physical']['gds_sha256'] or sha(folder/(NAME+'.lef'))!=r['physical']['lef_sha256']:raise ValueError('Counter GDS/LEF changed')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]+[ROOT/n for n in i['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    paths += certification_inputs()
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        external_files=i['pdk_files'],tools=i['tools'],cad=i['cad'],math_runtime=exact.math_runtime(),ports={p:r['physical']['ports'][p] for p in physical.PORTS},native_census=native,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or physical.native.environment.tools()!=i['tools'] or sha(Path(physical.original.repaired.CAD))!=i['cad']['sha256'] or exact.math_runtime()!=i['math_runtime']
        or list(i['ports'])!=physical.PORTS or i['native_census']['native_model_counts']!=EXPECTED):raise ValueError('Repaired counter full RC context changed')
    return m


def certify(out,info,reference):
    proofdir=out/'proof';proofdir.mkdir();code='''import sys,json
from pathlib import Path
sys.path.insert(0,'scripts');import build_parallel_output_cell_v111 as p
out=Path(sys.argv[1]);info=json.loads((out/'extraction.json').read_text());result=p.certify(out/'proof',info,sys.argv[2],Path(sys.argv[3]),494)
print(json.dumps(result))
'''
    p=subprocess.run([physical.original.repaired.CAD,'-c',code,str(out),NAME,str(reference)],cwd=ROOT,capture_output=True,text=True)
    (out/'certify.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise ValueError('Full counter native/passive/Schur proof refused:\n'+p.stderr[-2500:])
    return json.loads(p.stdout)


def run(out):
    m=bound(out);i=m['identity'];parent=ROOT/i['parent'];folder=parent/NAME;gds=folder/(NAME+'.gds')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial full counter extraction')
        atomic(out/'state.json',dict(status='extracting',qualified_phy=False))
        try:
            digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()[:16]
            if (ROOT/'build/extracted'/digest/NAME).exists():raise ValueError('Retain existing exact GDS counter extraction')
            reference=folder/(NAME+'.lvs.spice');info=extractor.extract(NAME,gds,sha(parent/'manifest.json'),ports=i['ports'],source_scope=sha(reference))
            atomic(out/'extraction.json',info)
            if not info['passed'] or not info['ports_verified'] or info['ports']!=physical.PORTS:raise ValueError('Actual counter RC extraction, passivity or interface failed')
            proof=certify(out,info,reference)
            if proof['independent_terminal_current_witness']['runtime']!=i['math_runtime']:raise ValueError('Independent counter RC math environment changed')
            bound(out)
            result=dict(extraction=info,rc_proof=proof,native_census=i['native_census'],counter_shared_wire_rc_qualified=True,compact_counter_shared_wire_rc_qualified=True,
                counter_timing_qualified=False,all_pvt_covered=False,corrected_dcc_output_qualified=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            result['files']={str(p.relative_to(out)):sha(p) for p in out.glob('**/*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
            result['extracted_files']={str((ROOT/info[k]).relative_to(ROOT)):sha(ROOT/info[k]) for k in ('raw_netlist','netlist')}
            atomic(out/'summary.json',result);atomic(out/'state.json',dict(status='complete',passed=True,qualified_phy=False));return out
        except Exception as e:atomic(out/'state.json',dict(status='failed',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
