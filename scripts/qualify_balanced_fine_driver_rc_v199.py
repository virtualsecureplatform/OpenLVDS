#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh native distributed RC qualification of both balanced fine drivers."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import build_balanced_fine_driver_v198 as physical
import build_parallel_output_cell_v111 as proof
import extract_native_flat_v4 as extractor
import native_bank_inventory_v51 as inventory

ROOT=physical.ROOT
VERSION='balanced-regular-pn-driver-native-distributed-rc-v199.1'
CONTEXT='balanced_fine_driver_rc_v199'
SCOPE='Exact balanced driver GDS local RC, native topology/parameters, passive reduction and independent terminal-current proof only; no bank timing/all-PVT/PHY admission'
atomic=physical.atomic


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def census(text,name,spec):
    ports,devices=inventory.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',text),name+'_flat')
    expected={'sky130_fd_pr__nfet_01v8':spec['n_fingers'],'sky130_fd_pr__pfet_01v8':spec['p_fingers'],physical.CAP:1}
    counts=dict(Counter(d['model'] for d in devices))
    if ports!=physical.PORTS or counts!=expected:raise ValueError('Balanced driver native inventory or public ports changed')
    return dict(ports=ports,native_model_counts=counts,native_primitives=len(devices))


def require_physical(state,report):
    if state!=dict(status='complete',passed=True,qualified_phy=False) or report.get('passed') is not True or len(report.get('rows',[]))!=2:
        raise ValueError('Require both complete passing balanced driver layouts')
    for row,spec in zip(report['rows'],physical.PROFILES):
        if row.get('spec')!=spec or row.get('macro')!=physical.name(spec) or any(row.get(k) is not True for k in ('passed','lvs_passed','native_inventory_passed')) or row.get('drc_count')!='0':
            raise ValueError('Balanced driver physical admission failed')


def prepare(parent):
    m=physical.bound(parent);i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    require_physical(json.loads((parent/'state.json').read_text()),r)
    paths=[parent/n for n in ('manifest.json','summary.json','state.json')]+[ROOT/n for n in i['inputs']]
    rows=[]
    for row in r['rows']:
        name=row['macro'];folder=parent/name
        if any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Balanced driver physical output changed')
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
        native=census((folder/(name+'.lvs.spice')).read_text(),name,row['spec'])
        if sha(folder/(name+'.gds'))!=row['gds_sha256']:raise ValueError('Balanced driver GDS changed')
        rows.append(dict(macro=name,spec=row['spec'],ports={p:row['ports'][p] for p in physical.PORTS},native_census=native))
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),rows=rows,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},external_files=i['external_files'],tools=i['tools'],math_runtime=proof.math_proof.math_proof()['runtime'],scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or physical.primitive.environment.tools()!=i['tools'] or proof.math_proof.math_proof()['runtime']!=i['math_runtime']):
        raise ValueError('Balanced driver RC context changed')
    physical.bound(ROOT/i['parent'])
    return m


def run(out):
    i=bound(out)['identity'];parent=ROOT/i['parent'];rows=[]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial balanced driver RC extraction')
        atomic(out/'state.json',dict(status='extracting',qualified_phy=False))
        try:
            for row in i['rows']:
                name=row['macro'];folder=parent/name;gds=folder/(name+'.gds');reference=folder/(name+'.lvs.spice')
                digest=hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()[:16]
                if (ROOT/'build/extracted'/digest/name).exists():raise ValueError('Retain existing exact balanced driver extraction')
                info=extractor.extract(name,gds,sha(out/'manifest.json'),ports=row['ports'],source_scope=sha(reference))
                target=out/name;target.mkdir();atomic(target/'extraction.json',info)
                if not info['passed'] or not info['ports_verified'] or info['ports']!=physical.PORTS:raise ValueError('Balanced driver RC interface/extraction failed')
                result=proof.certify(target,info,name,reference,row['native_census']['native_primitives'])
                if result['independent_terminal_current_witness']['runtime']!=i['math_runtime']:raise ValueError('Balanced driver independent math runtime changed')
                rows.append(dict(row,extraction=info,rc_proof=result,local_rc_qualified=True,bank_timing_qualified=False,qualified_phy=False))
                atomic(target/'summary.json',rows[-1])
            bound(out)
            report=dict(rows=rows,balanced_driver_local_rc_qualified=True,bank_timing_qualified=False,all_pvt_covered=False,qualified_phy=False,scope=SCOPE)
            report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
            report['extracted_files']={row['extraction'][k]:sha(ROOT/row['extraction'][k]) for row in rows for k in ('raw_netlist','netlist')}
            atomic(out/'summary.json',report);atomic(out/'state.json',dict(status='complete',passed=True,qualified_phy=False));return out
        except Exception as e:atomic(out/'state.json',dict(status='failed',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
