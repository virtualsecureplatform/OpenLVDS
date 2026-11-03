#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Static closed-loop common-mode impedance; no loop break or margin claim."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import numpy as np

import native_ac
import observe_compact_driver_loop as observer
import assemble_driver_compact_native as assembly
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
sha=assembly.sha
VIEWS=['schematic','native_core','native_core_bias']
SWEEP='.ac dec 80 10k 1G'
REFERENCE='https://ngspice.sourceforge.io/docs/ngspice-42-manual.pdf'


def fixture(deck,old,new,model,logic,probes):
    if logic not in [0.,1.8]: raise ValueError('Use the two original fixed data states')
    include=f'.include "{old}/source.spice"'
    if deck.count(include)!=1 or re.findall(r'(?im)^\.tran[^\n]+',deck)!=['.tran 1p 80n 0 1p']:
        raise ValueError('Require the original full native fixture as the DC/load reference')
    if len(re.findall(r'(?m)^VD D 0 PWL\([^\n]+\)',deck))!=1: raise ValueError('Expected original logic source')
    result=deck.replace(include,f'.include "{new}/source.spice"')
    result=re.sub(r'(?m)^VD D 0 PWL\([^\n]+\)',f'VD D 0 DC {logic:g}',result)
    result=re.sub(r'(?im)^\.(?:tran|print|save)[^\n]*\n','',result)
    result=re.sub(r'(?im)^\.options\s+device\s+temp=(\S+)',r'.temp \1',result)
    result=re.sub(r'(?im)^\.options\s+timeint\s+',r'.options ',result)
    first,rest=result.split('\n',1);result=first+'\n.options klu\n'+rest
    if result.splitlines().count('.end')!=1: raise ValueError('Unexpected AC fixture terminator')
    saved=['P','N',*probes.values()]
    result=result.replace('.end','IACP 0 P DC 0 AC 1u\nIACN 0 N DC 0 AC 1u\n'+SWEEP+'\n.save '+
        ' '.join('V('+n.replace(':','.')+')' for n in saved)+'\n.end')
    ProbeNetwork(model).validate(result,saved)
    return result


def impedance(names,wave):
    f=wave[:,names.index('frequency')]
    if (len(f)!=401 or not np.isfinite(wave).all() or not np.all(f.imag==0) or
            not np.isclose(f[0].real,1e4,rtol=1e-9) or not np.isclose(f[-1].real,1e9,rtol=1e-9) or
            np.any(np.diff(f.real)<=0)):
        raise ValueError('Incomplete or invalid declared AC frequency grid')
    p,n=[wave[:,names.index('v('+node+')')] for node in ['p','n']]
    # Vcm is normalized by the sum of both 1 uA injected currents.
    return f.real,(p+n)/2/(2e-6),p-n


def measure(raw):
    names,w=native_ac.read_complex(raw);f,z,diff=impedance(names,w);i=int(np.argmax(abs(z)))
    return dict(peak_hz=float(f[i]),peak_common_mode_impedance_ohm=float(abs(z[i])),
        peak_phase_deg=float(np.angle(z[i],deg=True)),
        low_frequency_impedance_ohm=float(abs(z[0])),high_frequency_impedance_ohm=float(abs(z[-1])),
        peak_is_bracketed=bool(0<i<len(f)-1),
        differential_response_at_peak_v=float(abs(diff[i])),frequency_points=len(f),
        scope='Closed-loop impedance about one static DC state; not loop gain, phase margin or switching stability sign-off.')


def prepare(observation):
    m=observer.bound(observation);i=m['identity'];assembled=ROOT/i['assembly']
    a=json.loads((assembled/'summary.json').read_text())
    if assembly.assemble(ROOT/a['identity']['extraction'])!=assembled: raise ValueError('Native assembly changed')
    models={'schematic':(assembled/'schematic.spice').read_text(),
            'native_core':(observation/'source.spice').read_text(),
            'native_core_bias':(assembled/'native.spice').read_text()}
    inputs=dict(i['inputs'])
    inputs.update({str((observation/n).relative_to(ROOT)):h for n,h in m['files'].items()})
    inputs[str((observation/'manifest.json').relative_to(ROOT))]=sha(observation/'manifest.json')
    code=dict(i['code'])
    code.update({n:sha(ROOT/'scripts'/n) for n in ['measure_driver_cm_impedance.py','native_ac.py','spice_slots.py']})
    identity=dict(observation=str(observation.relative_to(ROOT)),inputs=inputs,code=code,simulator=provenance(),
        views=VIEWS,data_logic_v=[0.,1.8],frequency_analysis=SWEEP,method_reference=REFERENCE,
        scope='Passive analytic calibration followed by six static TT25 closed-loop common-mode '
              'impedance diagnostics: source, native core/source bias, native core/native bias '
              'at both fixed logic states. Original supplies/reference/load retained. Equal '
              'zero-DC AC current perturbations at both output pins; no feedback break, '
              'supply voltage sweep, phase-margin claim or PHY admission.')
    out=ROOT/'build/diagnostics/driver_cm_impedance'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);tasks=[]
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for view in VIEWS:
            for logic in [0.,1.8]:
                name=view+('_negative' if logic==0 else '_positive');folder=out/name;folder.mkdir(exist_ok=True)
                if view=='schematic':
                    probes={n:'XD:XCORE:'+n for n in ['CM','CMS','SINK','TOP','BOT']}
                else:
                    probes={n:'XD:XCORE:'+i['observations'][n]['native_node'] for n in ['CM','CMS','SINK','TOP','BOT']}
                probes['NB']='XD:NB'
                deck=fixture((observation/'bench.cir').read_text(),observation,folder,models[view],logic,probes)
                for n,body in [('source.spice',models[view]),('bench.cir',deck)]:
                    p=folder/n
                    if p.exists() and p.read_text()!=body: raise ValueError('Prepared common-mode AC fixture changed')
                    if not p.exists():p.write_text(body)
                tasks.append(dict(id=name,view=view,logic_v=logic,files={n:sha(folder/n) for n in ['source.spice','bench.cir']}))
        folder=out/'calibration';folder.mkdir(exist_ok=True)
        calibration='''OpenLVDS common-mode AC normalization calibration
.options klu
RP P 0 100
RN N 0 100
CP P 0 2p
CN N 0 2p
IACP 0 P DC 0 AC 1u
IACN 0 N DC 0 AC 1u
'''+SWEEP+'\n.save V(P) V(N)\n.end\n'
        path=folder/'bench.cir'
        if path.exists() and path.read_text()!=calibration: raise ValueError('AC calibration changed')
        if not path.exists():path.write_text(calibration)
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,
            calibration=dict(id='calibration',files={'bench.cir':sha(path)}),qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    expected=[(v,l) for v in VIEWS for l in [0.,1.8]]
    if (not out.is_relative_to(ROOT/'build/diagnostics/driver_cm_impedance') or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            [(t['view'],t['logic_v']) for t in m['tasks']]!=expected or
            provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
            any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
            any(sha(out/t['id']/n)!=h for t in [m['calibration'],*m['tasks']] for n,h in t['files'].items())):
        raise ValueError('Common-mode AC context changed')
    return m


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    previous=native_ac.slot
    try:
        # native_ac.run owns the sole SPICE lease; there is no outer lease.
        native_ac.slot=lambda:lease(ROOT,priority=2,label='driver_cm_impedance')
        with (out/'.execution.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if (out/'state.json').exists() or any((out/t['id']/'bench.raw').exists() for t in [m['calibration'],*m['tasks']]):
                raise ValueError('Prior or partial common-mode AC run retained')
            atomic(out/'state.json',dict(status='waiting_for_ac_calibration',qualified_phy=False))
            raw=native_ac.run(out/'calibration/bench.cir');bound(out)
            names,w=native_ac.read_complex(raw);f,z,_=impedance(names,w)
            exact=50/(1+2j*np.pi*f*100*2e-12)
            error=float(np.max(abs(z-exact)/abs(exact)))
            calibration=dict(passed=error<=1e-6,max_relative_error=error,definition='Vcm divided by total 2 uA; two parallel 100 ohm/2 pF shunts')
            capture_manifest(out/'calibration/summary.json',calibration)
            if not calibration['passed']: raise ValueError('Common-mode AC normalization calibration failed')
            rows=[]
            for task in m['tasks']:
                bound(out);atomic(out/'state.json',dict(status='running_'+task['id'],qualified_phy=False))
                raw=native_ac.run(out/task['id']/'bench.cir');bound(out)
                row=dict(task=task['id'],**measure(raw));capture_manifest(out/task['id']/'summary.json',row);rows.append(row)
            files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.suffix in ['.raw','.log','.json'] and p.name not in ['manifest.json','state.json','summary.json']}
            capture_manifest(out/'summary.json',dict(calibration=calibration,results=rows,required=6,
                diagnostic_complete=True,manifest_sha256=stamp,files=files,qualified_phy=False,scope=m['identity']['scope']))
            atomic(out/'state.json',dict(status='completed_static_cm_impedance',qualified_phy=False))
    finally:native_ac.slot=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
