#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Characterize the current 16x32 TX bank at fifteen PVT, then propose an order.

The raw table uses 410 MHz/50% duty. Selected/boundary clock sweeps, safe
updates, alternative bank dimensions, RX range and physical ROM remain gates.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_regular_regenerated_dense_v294 as dense
import probe_regular_regenerated_pvt_v291 as sparse
from run_regular_regenerated_dense_v295 import require_curve
from run_regular_regenerated_pvt_v292 import require_matrix
import common_delay_sequence_v296 as selector
from clocking_v2 import Delay
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease

source=sparse.source
ROOT=source.ROOT
sha=source.sha
VERSION='actual-regular-pair-full-16x32-tx-fifteen-pvt-reference-clock-v301.1'
CONTEXT='regular_regenerated_full_range_v301'
SCOPE='7680 routed 16x32 TX raw-code/PVT points at 410MHz/50% duty; common ordering is a proposal, selected/boundary clocks, updates, other dimensions, RX, ROM and PHY remain unqualified'


def key(spec):return json.dumps(spec,sort_keys=True)


def specifications():
    sparse.specifications()  # Fixed supplies and approved clock/PVT contract.
    selector.policy('tx',16,32)
    return [dict(source.native.spec(),process=p,temperature=t,coarse=c,fine=f,
        frequency_mhz=410,duty=.5,cycles=8,stop_ns=25)
        for p in ('tt','ff','ss','fs','sf') for t in (0,25,40)
        for c in range(16) for f in range(32)]


def assess(rows):
    matrix=specifications()
    if len(rows)!=len(matrix) or any(r.get('error') is not None or r.get('result') is None for r in rows):return None
    actual=[key(r['spec']) for r in rows]
    if len(set(actual))!=7680 or set(actual)!={key(s) for s in matrix}:
        raise ValueError('Require complete unique 512-code coverage at all fifteen PVT and exact reference clock')
    native=all(sparse.point_passed(r['result']) for r in rows)
    # Never discard a startup edge, average a history, or merge PVT offsets.
    intervals=[];corners={p:dict(rise=[],fall=[]) for p in selector.PVT}
    if native:
        for row in rows:
            s=row['spec'];v=row['result'];corner=s['process']+':'+str(s['temperature']);code=s['coarse']*32+s['fine']
            edges={edge:dict(lo_ps=min(v['edge_delays_ps'][edge]),hi_ps=max(v['edge_delays_ps'][edge])) for edge in ('rise','fall')}
            intervals.append(dict(pvt=corner,code=code,coarse=s['coarse'],fine=s['fine'],edges=edges))
            for edge in ('rise','fall'):corners[corner][edge].append(Delay(code,**edges[edge]))
    proposal=selector.select(corners,'tx',16,32) if native else None
    return dict(complete_7680_point_coverage=True,all_fifteen_pvt_raw_curves_characterized=native,
        full_current_16x32_raw_range_characterized=native,all_native_points_passed=native,
        delay_intervals=sorted(intervals,key=lambda r:(r['pvt'],r['code'])),proposed_common_sequence=proposal,
        common_sequence_found=bool(proposal and proposal['common_sequence_found']),
        all_clock_conditions_characterized=False,bank_configuration_selected=False,
        legal_code_table_admitted=False,updates_qualified=False,rx_range_qualified=False,
        physical_rom_qualified=False,whole_clock_qualified=False,electrical_qualification_passed=False,qualified_phy=False)


def fixture(out,i,s):
    text=source.fixture(out,i,s);title='OpenLVDS '+source.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original routed periodic fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def completed_parent(parent,module,require):
    m=module.bound(parent);i=m['identity'];report=require(parent)
    if report['inherited_rows']!=i['inherited_rows'] or [r['task'] for r in report['rows']]!=m['tasks']:
        raise ValueError('Parent rows do not match bound inherited records and tasks')
    if report['comparison']!=module.assess(report['inherited_rows']+report['rows'],i['matrix']):
        raise ValueError('Parent complete metrics do not reproduce')
    origin=ROOT/i['parent'];origin_m=source.bound(origin)
    rows=[];paths=[parent/n for n in ('manifest.json','summary.json','state.json','bank.spice')]
    for inherited,group in ((True,report['inherited_rows']),(False,report['rows'])):
        for row in group:
            case=(origin if inherited else parent)/row['task']['id']
            if (row!=json.loads((case/'summary.json').read_text())
                or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(row['files'])
                or any(sha(case/n)!=h for n,h in row['files'].items())
                or sha(case/'bench.cir')!=row['task']['deck_sha256']):
                raise ValueError('Completed native parent trace changed')
            measured=(source.measure(case,dict(origin_m['identity'],spec=row['spec'])) if inherited
                else module.measure(case,i,row['spec']))
            if measured!=row['result']:raise ValueError('Complete original native parent metrics do not reproduce')
            rows.append(dict(case=str(case.relative_to(ROOT)),row=row))
            paths += [case/'summary.json',*[case/n for n in row['files']]]
    paths += [ROOT/n for n in i['inputs']]
    return m,rows,paths


def reuse(sparse_rows,dense_rows):
    # The three shared donor cases must agree in source, task, files and metrics.
    lookup={}
    for item in sparse_rows+dense_rows:
        k=key(item['row']['spec'])
        if k in lookup and lookup[k]!=item:raise ValueError('Overlapping donor native evidence differs')
        lookup[k]=item
    wanted={key(s) for s in specifications()}
    selected=[lookup[k] for k in sorted(wanted & lookup.keys())]
    if len(selected)!=106:raise ValueError('Require exactly 106 matching full-range donor conditions')
    return selected


def prepare(sparse_parent,dense_parent):
    sm,sr,paths=completed_parent(sparse_parent,sparse,require_matrix)
    dm,dr,more=completed_parent(dense_parent,dense,require_curve);paths+=more
    si=sm['identity'];di=dm['identity']
    if (si['parent']!=di['parent'] or sm['bank_sha256']!=dm['bank_sha256']
        or si['observations']!=di['observations'] or si['pdk_files']!=di['pdk_files']
        or si['model']!=di['model'] or si['simulator']!=di['simulator']):
        raise ValueError('Sparse and dense donors must share the exact routed bank and native models')
    inherited=reuse(sr,dr);old={key(r['row']['spec']) for r in inherited}
    matrix=specifications();specs=[s for s in matrix if key(s) not in old]
    if len(specs)!=7574:raise ValueError('Require 7574 new raw-code/PVT cases')
    paths += [ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'clocking_duty_v2_2.json']
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None)
        and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    base={k:v for k,v in si.items() if k not in ('matrix','inherited_rows')}
    i=dict(base,version=VERSION,sparse_parent=str(sparse_parent.relative_to(ROOT)),dense_parent=str(dense_parent.relative_to(ROOT)),
        inherited_sources=inherited,specs=specs,inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},
        max_workers=2,priority=2,numpy_version=source.np.__version__,byteorder=sys.byteorder,scope=SCOPE)
    # Per-case decks are generated lazily from these bound specs. Preparation
    # does not create thousands of unused folders while prerequisites are absent.
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((sparse_parent/'bank.spice').read_bytes())
    atomic(out/'manifest.json',dict(identity=i,bank_sha256=sha(out/'bank.spice'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];origin=i['inherited_sources']
    old={key(r['row']['spec']) for r in origin}
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or source.zero.engine()!='ngspice' or source.zero.provenance()!=i['simulator']
        or i['numpy_version']!=source.np.__version__ or i['byteorder']!=sys.byteorder
        or i['max_workers']!=2 or i['priority']!=2 or len(origin)!=106 or len(old)!=106
        or len(i['specs'])!=7574
        or len(i['observations']['devices'])!=1529 or len(i['observations']['programming_gates'])!=173
        or sha(Path(source.native.CAD))!=i['cad']['sha256']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(out/'bank.spice')!=m['bank_sha256']
        or any(sha(ROOT/i[parent]/'bank.spice')!=m['bank_sha256'] for parent in ('sparse_parent','dense_parent'))
        or i['specs']!=[s for s in specifications() if key(s) not in old]
        or any(r['row']!=json.loads((ROOT/r['case']/'summary.json').read_text()) or not sparse.point_passed(r['row']['result']) for r in origin)):
        raise ValueError('Full-range routed native context changed')
    return m


def measure(case,i,s):return dict(source.measure(case,dict(i,spec=s)),scope=SCOPE)


def execution_bound(out,m,manifest_sha):
    """Guard runtime sources/models per lease; rehash all donor data at both ends."""
    i=m['identity']
    runtime={n:h for n,h in i['inputs'].items() if n.startswith('scripts/') or n in
        ('requirements.json','clocking_v2.json','clocking_duty_v2_2.json')}
    if (sha(out/'manifest.json')!=manifest_sha or sha(out/'bank.spice')!=m['bank_sha256']
        or any(sha(ROOT/n)!=h for n,h in runtime.items())
        or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i.get('external_files',{})}.items())
        or sha(Path(source.native.CAD))!=i['cad']['sha256']
        or source.zero.engine()!='ngspice' or source.zero.provenance()!=i['simulator']):
        raise ValueError('Full-range native runtime sources or models changed')


def run(out):
    m=bound(out);i=m['identity'];manifest_sha=sha(out/'manifest.json')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial full-range native campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(item):
            k,s=item;case=out/str(k);result=error=None
            case.mkdir();(case/'bench.cir').write_text(fixture(out,i,s))
            task=dict(id=str(k),spec=s,deck_sha256=sha(case/'bench.cir'))
            try:
                with lease(ROOT,priority=i['priority'],label=CONTEXT+'_'+str(k)):
                    execution_bound(out,m,manifest_sha)
                    if (case/'bench.cir').read_text()!=fixture(out,i,s):raise ValueError('Full-range fixture changed')
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(case/'ngspice.log'),str(case/'bench.cir')],capture_output=True,text=True)
                (case/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(case,i,s)
            except Exception as e:error=str(e)
            row=dict(task=task,spec=s,result=result,error=error,files={p.name:sha(p) for p in case.iterdir() if p.is_file()})
            atomic(case/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,enumerate(i['specs'])))
        bound(out);inherited=[r['row'] for r in i['inherited_sources']]
        atomic(out/'summary.json',dict(rows=rows,inherited_rows=inherited,comparison=assess(inherited+rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=7680,consumed_cases=106,errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


def verify(out):
    m=bound(out);i=m['identity'];r=json.loads((out/'summary.json').read_text())
    if (json.loads((out/'state.json').read_text())!=dict(status='complete',cases=7680,consumed_cases=106,errors=0,qualified_phy=False)
        or len(r.get('rows',[]))!=7574 or r.get('inherited_rows')!=[s['row'] for s in i['inherited_sources']]):
        raise ValueError('Full-range native characterization incomplete or failed')
    for k,(spec,row) in enumerate(zip(i['specs'],r['rows'])):
        case=out/str(k);deck=case/'bench.cir'
        if (row.get('task')!=dict(id=str(k),spec=spec,deck_sha256=sha(deck)) or row.get('spec')!=spec
            or row.get('error') is not None or row!=json.loads((case/'summary.json').read_text())
            or not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(row['files'])
            or any(sha(case/n)!=h for n,h in row['files'].items()) or deck.read_text()!=fixture(out,i,spec)
            or measure(case,i,spec)!=row['result']):
            raise ValueError('Complete full-range native metrics do not reproduce')
    comparison=assess(r['inherited_rows']+r['rows'])
    if comparison!=r.get('comparison') or not comparison['all_native_points_passed']:
        raise ValueError('Full-range native interval or common-order result does not reproduce')
    bound(out);return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    for action in ('prepare','campaign'):
        q=sub.add_parser(action);q.add_argument('sparse',type=Path);q.add_argument('dense',type=Path)
    for action in ('run','verify'):
        q=sub.add_parser(action);q.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve() if a.action in ('run','verify') else prepare(a.sparse.resolve(),a.dense.resolve())
    print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
    if a.action=='verify':verify(out)
