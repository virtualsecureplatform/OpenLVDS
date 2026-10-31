#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture and audit further exact algebraic reduction of an isolated DLL network."""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from dll_campaign import atomic
from dll_candidate_library import audited
from reduce_rc import eliminate,number
from spice_library import checked_netlist

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(text):
    graph=defaultdict(dict);protected={'0'};kept=[];header=False;subcircuits=0;resistors=0
    for line in text.splitlines():
        w=line.split()
        if not w or w[0].startswith('*'):kept.append(line);continue
        tag=w[0].lower()
        if tag=='.subckt':protected.update(w[2:]);header=True;subcircuits+=1
        elif tag=='+':
            if header:protected.update(w[1:])
        else:header=False
        if tag.startswith('r'):
            if len(w)!=4:raise ValueError('Only constant two-terminal resistors can be eliminated')
            a,b=w[1:3];r=number(w[3]);resistors+=1
            if not math.isfinite(r) or r<=0 or not math.isfinite(1/r):raise ValueError('Non-positive or invalid resistance')
            if a!=b:
                g=1/r;graph[a][b]=graph[a].get(b,0)+g;graph[b][a]=graph[b].get(a,0)+g
            continue
        kept.append(line)
        if tag.startswith('c'):protected.update(w[1:3])
        elif tag.startswith('x'):
            end=next((i for i,v in enumerate(w) if '=' in v),len(w));protected.update(w[1:end-1])
        elif tag.startswith('m'):protected.update(w[1:5])
        elif tag.startswith(('v','i','l','b','d')):protected.update(w[1:3])
        elif tag=='.global':protected.update(w[1:])
    if subcircuits!=1 or sum(line.lower().startswith('.ends') for line in kept)!=1:
        raise ValueError('Expected one flattened subcircuit')
    return dict(graph=dict(graph),protected=protected,kept=kept,resistors=resistors)


def static_signature(network):
    return hashlib.sha256('\n'.join(line for line in network['kept'] if line.strip() and not line.lstrip().startswith('*')).encode()).hexdigest()


def render(network,degree):
    lines=[]
    for a in sorted(network['graph']):
        for b,g in sorted(network['graph'][a].items()):
            if a>=b:continue
            if not math.isfinite(g) or g<=0:raise ValueError('Invalid reduced conductance')
            lines.append(f'RKRON{len(lines)} {a} {b} {1/g:.17g}')
    kept=list(network['kept']);end=next(i for i,line in enumerate(kept) if line.lower().startswith('.ends'))
    kept[end:end]=[f'* Exact algebraic star-mesh reduction, maximum elimination degree {degree}',*lines]
    return '\n'.join(kept)+'\n'


def boundary_currents(graph,protected,voltages):
    """Independent sparse Dirichlet solve; the elimination algorithm is not used."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse.linalg import splu
    names=sorted(graph);index={name:i for i,name in enumerate(names)}
    boundary=sorted(set(graph)&protected);bi=np.array([index[n] for n in boundary],int)
    if not len(boundary):raise ValueError('No observable resistor-network terminals')
    rows=[];cols=[];values=[]
    for a,neighbors in graph.items():
        i=index[a]
        for b,g in neighbors.items():
            rows.extend([i,i]);cols.extend([i,index[b]]);values.extend([g,-g])
    y=coo_matrix((values,(rows,cols)),shape=(len(names),len(names))).tocsr()
    count,labels=connected_components(y,directed=False)
    anchored=set(labels[bi]);gauges=[int(np.flatnonzero(labels==c)[0]) for c in range(count) if c not in anchored]
    known=np.r_[bi,np.array(gauges,int)];unknown=np.setdiff1d(np.arange(len(names)),known)
    v=np.zeros((len(names),voltages.shape[1]));v[bi]=voltages
    residual=0.
    if len(unknown):
        interior=y[unknown][:,unknown].tocsc();rhs=-(y[unknown][:,known]@v[known])
        v[unknown]=splu(interior).solve(rhs)
        error=interior@v[unknown]-rhs
        scale=np.maximum(np.max(abs(rhs)),1.)
        residual=float(np.max(abs(error))/scale)
    return boundary,np.asarray(y[bi]@v),dict(nodes=len(names),floating_components=len(gauges),relative_solver_residual=residual)


def witness(reference,reduced,count=4):
    boundary=sorted(set(reference['graph'])&reference['protected'])
    if boundary!=sorted(set(reduced['graph'])&reduced['protected']):raise ValueError('Protected resistor terminal removed')
    voltages=np.random.default_rng(1308).uniform(-1,1,(len(boundary),count))
    if '0' in boundary:voltages[boundary.index('0')]=0
    _,a,old=boundary_currents(reference['graph'],reference['protected'],voltages)
    _,b,new=boundary_currents(reduced['graph'],reduced['protected'],voltages)
    delta=abs(a-b);normalized=delta/(1e-9+1e-8*np.maximum(abs(a),abs(b)))
    passed=bool(np.max(normalized)<=1 and max(old['relative_solver_residual'],new['relative_solver_residual'])<=1e-10)
    return dict(passed=passed,witnesses=count,seed=1308,boundary_nodes=len(boundary),
        current_absolute_error_max_a=float(np.max(delta)),normalized_current_error_max=float(np.max(normalized)),
        relative_tolerance=1e-8,absolute_tolerance_a=1e-9,reference=old,reduced=new,
        scope='Random clamped-terminal DC witnesses plus invariant capacitor/device/port statements; native transient comparison remains required')


def math_runtime():
    import scipy
    import scipy.sparse._sparsetools as sparse
    import scipy.sparse.linalg._dsolve._superlu as solver
    files=[Path(np._core._multiarray_umath.__file__),Path(sparse.__file__),Path(solver.__file__)]
    for package in [np,scipy]:files+=sorted((Path(package.__file__).parents[1]/(package.__name__+'.libs')).glob('*.so*'))
    return dict(numpy=np.__version__,scipy=scipy.__version__,binaries={str(p.relative_to(ROOT)):digest(p) for p in files})


def prepare(layout,degree):
    layout=layout.resolve()
    if not layout.is_relative_to(ROOT/'build/diagnostics/dll_layout'):raise ValueError('Use an isolated DLL layout')
    physical=json.loads((layout/'summary.json').read_text());info=json.loads((layout/'extraction.json').read_text())
    if not physical['passed'] or digest(layout/'candidate.spice')!=physical['source_sha256']:raise ValueError('Physical source changed')
    gds=ROOT/physical['designs']['openlvds_dll_analog']['gds']
    if digest(gds)!=info['gds_sha256']:raise ValueError('Physical GDS changed')
    audited(layout,info);text=checked_netlist(info)
    identity=dict(layout=str(layout.relative_to(ROOT)),degree=degree,source_sha256=info['netlist_sha256'],
        physical_files={str(p.relative_to(ROOT)):digest(p) for p in [layout/'summary.json',layout/'extraction.json',layout/'rc_audit.json']},
        code={p.name:digest(p) for p in [Path(__file__),ROOT/'scripts/reduce_rc.py']},math_runtime=math_runtime())
    out=ROOT/'build/diagnostics/dll_layout'/('schur_'+hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16])
    out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():
        saved=json.loads((out/'manifest.json').read_text())
        if saved['identity']!=identity or any(digest(out/name)!=value for name,value in saved['files'].items()):
            raise ValueError('Exact candidate manifest or captured evidence changed')
        candidate=json.loads((out/'extraction.json').read_text());audited(out,candidate)
        print(out,flush=True);return out
    reference=parse(text);candidate=deepcopy(reference)
    removed=eliminate(candidate['graph'],candidate['protected'],degree)
    native=render(candidate,degree);serialized=parse(native)
    if static_signature(reference)!=static_signature(serialized) or reference['protected']!=serialized['protected']:
        raise ValueError('Algebraic reduction changed a capacitor, device, port or directive')
    result=witness(reference,serialized);atomic(out/'admittance_witness.json',result)
    if not result['passed']:raise ValueError('Independent sparse terminal-admittance witness failed')
    (out/'candidate.spice').write_bytes((layout/'candidate.spice').read_bytes())
    (out/'summary.json').write_bytes((layout/'summary.json').read_bytes())
    target=out/'openlvds_dll_analog.exact.spice';target.write_text(native)
    post=dict(source_sha256=info['netlist_sha256'],reduced_sha256=digest(target),degree=degree,
        resistor_count_before=reference['resistors'],resistor_count_after=serialized['resistors'],
        algebraic_nodes_eliminated=removed,non_resistor_sha256=static_signature(serialized),
        witness=str((out/'admittance_witness.json').relative_to(ROOT)),witness_sha256=digest(out/'admittance_witness.json'))
    reduction=info['reduction']
    newer=dict(info,netlist=str(target.relative_to(ROOT)),netlist_sha256=digest(target),
        reduction=dict(source_sha256=reduction['source_sha256'],reduced_sha256=digest(target),
            resistor_count_before=reduction['resistor_count_before'],resistor_count_after=serialized['resistors'],
            algebraic_nodes_eliminated=reduction['algebraic_nodes_eliminated']+removed,protected_nodes=len(serialized['protected']),
            method=f'exact positive-conductance star-mesh, original stage then degree <= {degree}',chain=[reduction,post]),
        exact_postprocessing=post,transient_equivalence_pending=True)
    atomic(out/'extraction.json',newer)
    audit=subprocess.run(['scripts/env.sh','--tools','--ngspice','python3','scripts/dll_candidate_rc.py',str(out.relative_to(ROOT))],
        cwd=ROOT,capture_output=True,text=True)
    (out/'independent_audit.log').write_text(audit.stdout+audit.stderr);audit.check_returncode()
    audited(out,newer)
    atomic(out/'manifest.json',dict(identity=identity,qualified=False,transient_equivalence_pending=True,
        files={name:digest(out/name) for name in ['candidate.spice','summary.json','extraction.json','rc_audit.json',
                                                'openlvds_dll_analog.exact.spice','admittance_witness.json']}))
    print(out,flush=True);return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layout',type=Path)
    p.add_argument('--degree',type=int,choices=[6,8,12],default=8);a=p.parse_args();prepare(a.layout,a.degree)


if __name__=='__main__':main()
