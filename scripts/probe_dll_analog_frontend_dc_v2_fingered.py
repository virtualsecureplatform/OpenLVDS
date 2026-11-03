#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the two-stage revision using explicitly observed legal-width fingers."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import numpy as np
import dll_analog_frontend_v2_fingered as policy
import probe_dll_analog_frontend_dc_v2 as original

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_analog_frontend_dc_v2_fingered'
sha=original.sha
OUTPUTS=original.OUTPUTS
screen=original.dc.screen
_measure=original.measurements
_analysis_lock=threading.Lock()


def measurements(values,task):
    if not all(np.isfinite(v) for v in values.values()):raise ValueError('Nonfinite parallel-device operating point')
    def read(vector,field):
        keys=[vector]
        if field in ('id','vdsat'):keys += [('i' if field=='id' else 'v')+'('+vector+')']
        found=[float(values[k]) for k in keys if k in values]
        if not found or any(v!=found[0] for v in found):raise ValueError('Missing/inconsistent actual finger parameter: '+vector)
        return found[0]
    vectors=policy.op_parameters();combined=dict(values);observed={};healthy=True
    logical=policy.original.op_parameters()
    for group,role in policy.groups().items():
        fingers=[]
        for i in range(role['fingers']):
            names={k:vectors[group+'_f'+str(i)+'_'+k] for k in ('id','gm','gds','vdsat')}
            p={k:read(v,k) for k,v in names.items()};fingers.append(dict(parameters=p,vectors=names))
        currents=np.array([abs(f['parameters']['id']) for f in fingers]);mean=float(np.mean(currents))
        uniformity=float(np.max(abs(currents-mean))/mean) if mean else None
        same_sign=abs(abs(sum(f['parameters']['id'] for f in fingers))-float(currents.sum()))<=1e-15
        passed=bool(uniformity is not None and uniformity<=.05 and same_sign and
                    all(abs(f['parameters']['gm'])>0 and f['parameters']['gds']>=0 and abs(f['parameters']['vdsat'])>0 for f in fingers))
        healthy=healthy and passed
        # Electrical aggregates, never fabricated saved vectors or voltage
        # aliases: signed currents/gm/gds sum; worst saturation magnitude wins.
        aggregates={k:sum(f['parameters'][k] for f in fingers) for k in ('id','gm','gds')}
        aggregates['vdsat']=max(abs(f['parameters']['vdsat']) for f in fingers)
        for field,value in aggregates.items():
            key=logical[group+'_'+field]
            if key in values:raise ValueError('Unfingered model vector unexpectedly present')
            combined[key]=value
        observed[group]=dict(finger_count=len(fingers),fingers=fingers,aggregates=aggregates,
                             current_uniformity_fraction=uniformity,passed=passed)
    analysis=SimpleNamespace(VARIANTS=policy.VARIANTS,P5=policy.P5,circuit=policy.circuit,
                             tail_roles=policy.tail_roles,op_parameters=policy.original.op_parameters)
    # The retained numerical limits consume explicit effective aggregates.
    # Serialize this short analysis profile; SPICE execution remains parallel.
    with _analysis_lock:
        previous=original.policy
        try:original.policy=analysis;result=_measure(combined,task)
        finally:original.policy=previous
    result.update(parallel_device_observations=observed,parallel_devices_passed=bool(healthy),
                  parameter_aggregation='Signed id/gm/gds sums and maximum absolute vdsat over actual saved parallel fingers',
                  passed=bool(result['passed'] and healthy))
    return result


def invalid_context(out):
    if not out.is_relative_to(ROOT/'build/diagnostics'/original.NAMESPACE):raise ValueError('Require the retained invalid-width revision')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);original.bound(out)
        reports=list(out.glob('*/summary.json'))
        if not reports or any(json.loads(p.read_text())['error'] is None or 'could not find a valid modelname' not in (p.parent/'ngspice.log').read_text() for p in reports):
            raise ValueError('Require the known PDK model-bin failure; retain unrelated failures for diagnosis')
        return {str(p.relative_to(ROOT)):sha(p) for p in out.rglob('*') if p.is_file()}


@contextmanager
def profile(extra_inputs=None):
    previous=original.policy,original.NAMESPACE,original.measurements,original.failed_context
    admitted=original.failed_context
    def gate(parent):
        pm=deepcopy(admitted(parent))
        for name in (Path(__file__).name,'dll_analog_frontend_v2_fingered.py'):
            pm['identity']['code'][name]=sha(ROOT/'scripts'/name)
        pm['identity']['inputs'].update(extra_inputs or {})
        return pm
    try:
        original.policy=policy;original.NAMESPACE=NAMESPACE;original.measurements=measurements;original.failed_context=gate
        yield
    finally:original.policy,original.NAMESPACE,original.measurements,original.failed_context=previous


def prepare(failed,invalid):
    inputs=invalid_context(invalid)
    with profile(inputs):return original.prepare(failed)


def bound(out):
    with profile():return original.bound(out)


def run(out):
    with profile():return original.run(out)


def verify(out):
    with profile():return original.verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','bound','run','verify']);p.add_argument('artifact',type=Path);p.add_argument('--invalid',type=Path)
    a=p.parse_args()
    if a.action=='prepare':
        if not a.invalid:p.error('--invalid required')
        result=prepare(a.artifact.resolve(),a.invalid.resolve())
    else:result=globals()[a.action](a.artifact.resolve())
    print(result if a.action=='prepare' else json.dumps(result,indent=2),flush=True)
