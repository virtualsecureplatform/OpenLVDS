#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh LVDS pin fixtures with native DDR loading; bounded screening, no PHY release."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from dll_campaign import atomic, text_block
from dll_candidate_library import audited
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_library import checked_netlist, replace
from spice_probes import ProbeNetwork
from simulate_link import edge_times, word_stream, decode_public_pairs
from diagnose_link_clock import pulse_transport
from layout import circuits, flatten, schematic_text

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
CODE=['receiver_spec_screen.py','dll_campaign.py','dll_candidate_library.py','dll_measurements.py',
      'receiver_static_diagnosis.py','spice_dispatch.py','spice_slots.py','spice_engine.py',
      'spice_library.py','spice_probes.py','run_ngspice.py','simulate_link.py','diagnose_link_clock.py','layout.py']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def policy():return json.loads((ROOT/'receiver_acceptance.json').read_text())


def cases(req):
    result=[dict(id=f'native_rate_{mhz}',view='native',test='rate',process='ss',temperature=40,mhz=mhz)
            for mhz in policy()['native_screen']['clock_mhz']]
    result += [dict(id=f'{view}_wide_{p}_{t}',view=view,test='wide',process=p,temperature=t)
               for view in ['schematic','native'] for p in req['process_corners'] for t in req['temperatures_c']]
    return result


def pin_wave(events,initial,amplitude,common_mode,transition_ps):
    """Symmetric piecewise-linear input with specified 20--80 percent slew."""
    half=transition_ps/0.6/2000
    points=[(0,initial)];last=initial
    for at,value in events:
        if value==last:continue
        if at-half<=points[-1][0]:raise ValueError('Overlapping pin transitions')
        points.extend([(at-half,last),(at+half,value)]);last=value
    def source(sign):return 'PWL('+' '.join(f'{t:.12g}n {common_mode+sign*(2*v-1)*amplitude/2:.12g}' for t,v in points)+')'
    return source(1),source(-1)


def rate_events(mhz):
    period=1000/mhz;words=word_stream(40);clock=[];data=[]
    for n,word in enumerate(words):
        rise=5+n*period;fall=rise+period/2
        clock.extend([(rise,1),(fall,0)])
        data.extend([(rise-period/4,word&1),(fall-period/4,(word>>1)&1)])
    return clock,data,words


def fixture(parent,folder,task,lib):
    # Reuse the original fixed supplies, native RX instance and native bias.
    rows=[]
    for line in parent.splitlines():
        if line.startswith(('.lib ','.options ','VD ','VA ','VR ','IB ','XB ','VRST ','XRC ','XRD ','XRX ','CQ0 ','CQ1 ')):rows.append(line)
    if len(rows)!=14:raise ValueError('Unexpected loaded native receiver fixture')
    rows=[re.sub(r'"\s+ss$',f'" {task["process"]}',s) if s.startswith('.lib ') else s for s in rows]
    rows=[f'.options device temp={task["temperature"]}' if s.startswith('.options device temp=') else s for s in rows]
    rows.insert(0,'OpenLVDS specification pin screen; no PHY qualification')
    rows.insert(2,f'.include "{folder}/library.spice"')
    screen=policy()['native_screen']
    if task['test']=='rate':
        clock,data,_=rate_events(task['mhz'])
        cp,cn=pin_wave(clock,0,screen['differential_v'],screen['common_mode_v'],screen['transition_20_80_ps'])
        dp,dn=pin_wave(data,0,screen['differential_v'],screen['common_mode_v'],screen['transition_20_80_ps'])
        stop=screen['stop_ns']
    else:
        # Three valid common modes, each tested with both differential polarities.
        points_p=[];points_n=[]
        for n,cm in enumerate(policy()['wide_static_common_mode_v']):
            for bit in [0,1]:
                at=(2*n+bit)*12;diff=(2*bit-1)*policy()['wide_static_differential_v']
                for points,value in [(points_p,cm+diff/2),(points_n,cm-diff/2)]:
                    if at:points.extend([(at-.1,points[-1][1]),(at+.1,value)])
                    else:points.append((0,value))
        render=lambda ps:'PWL('+' '.join(f'{t:.12g}n {v:.12g}' for t,v in ps)+')'
        cp=dp=render(points_p);cn=dn=render(points_n);stop=72
    rows += [f'VRCP RCP 0 {cp}',f'VRCN RCN 0 {cn}',f'VRP RP 0 {dp}',f'VRN RN 0 {dn}']
    probes=['RCP','RCN','RP','RN','RXCLOCK','RXDATA','Q0','Q1','VALID']
    # Observe both restoring paths as well as the actual digital capture terminals.
    for instance in ['XRC','XRD']:
        for leaf in ['CO','CL','RESTORE0','RESTORE1']:
            candidates=sorted(set(re.findall(r'\b'+TOP+'__'+leaf+r'(?:\.(?:t|n)\d+)?\b',text_block(lib,TOP))))
            if not candidates:raise ValueError('Missing restoring observation '+leaf)
            probes.append(instance+':'+candidates[0])
    digital=text_block(lib,'openlvds_ddr_rx')
    for prefix in ['serial','clk']:
        probes += ['XRX:'+n for n in sorted(set(re.findall(r'\b'+prefix+r'\.(?:t|n)\d+\b',digital)))]
    rows += [f'.tran 5p {stop}n 0 1p','.print tran '+' '.join('V('+p+')' for p in probes),'.end']
    deck='\n'.join(rows)+'\n';ProbeNetwork(lib).validate(deck,probes)
    return deck,stop


def valid_widths(t,v,start,end):
    result={}
    for high,label in [(True,'high'),(False,'low')]:
        # Full valid-level pulse, not merely a .9 V crossing.
        enters=edge_times(t,v,1.44 if high else .36,high)
        exits=edge_times(t,v,1.44 if high else .36,not high)
        widths=[]
        for at in enters:
            after=exits[exits>at]
            if len(after) and start<=at<after[0]<=end:widths.append(float((after[0]-at)*1e12))
        result[label]=dict(count=len(widths),minimum_ps=min(widths) if widths else None)
    return result


def measure(w,h,task):
    t=w[:,1];stop=80 if task['test']=='rate' else 72
    if not np.isfinite(w).all() or t[0]>1e-15 or t[-1]<stop*1e-9-1e-12 or np.any(np.diff(t)<=0):raise ValueError('Incomplete specification screen waveform')
    v=lambda n:w[:,h['V('+n.upper()+')']]
    pins=np.column_stack([v(n) for n in ['RP','RN','RCP','RCN']]);lo,hi=policy()['pin_range_v']
    pin_ok=bool(pins.min()>=lo-1e-9 and pins.max()<=hi+1e-9)
    if task['test']=='wide':
        points=[]
        for index in range(6):
            values={n:float(np.interp((index*12+10)*1e-9,t,v(n))) for n in ['RXDATA','RXCLOCK']}
            points.append(dict(index=index,expected=index%2,outputs_v=values,
                passed=all(x>1.44 if index%2 else x<.36 for x in values.values())))
        return dict(passed=pin_ok and all(p['passed'] for p in points),pin_range_v=[float(pins.min()),float(pins.max())],points=points)
    s=policy()['native_screen'];start,end=np.array(s['observation_ns'])*1e-9
    transport=pulse_transport(t,v('RCP')-v('RCN'),v('RXCLOCK'),start,end)
    widths=valid_widths(t,v('RXCLOCK'),start,end)
    clock_ok=bool(len(transport['pulses'])>=35 and all(p['output_edges_in_next_input_period']==1 for p in transport['pulses']) and
        all(p['count']>=15 and p['minimum_ps']>=s['minimum_valid_pulse_ps'] for p in widths.values()))
    publication=edge_times(t,v('RXCLOCK'),rising=True)
    publication=publication[(publication>=start)&(publication+1.05e-9<t[-1])]
    decoded=decode_public_pairs(t,v('Q0'),v('Q1'),v('VALID'),publication).tolist()
    _,_,words=rate_events(task['mhz']);first=s['payload_first_word'];expected=words[first:first+s['payload_words']]
    matches=[i for i in range(len(decoded)-len(expected)+1) if decoded[i:i+len(expected)]==expected]
    payload_ok=len(matches)==1
    # Timing is reported before aperture subtraction; it cannot certify 200 ps margin.
    sampling=edge_times(t,v('RXCLOCK'));data_edges=edge_times(t,v('RXDATA'));setup=[];hold=[]
    for at in sampling[(sampling>=start)&(sampling<=end)]:
        before=data_edges[data_edges<at];after=data_edges[data_edges>at]
        if len(before):setup.append(float((at-before[-1])*1e12))
        if len(after):hold.append(float((after[0]-at)*1e12))
    return dict(passed=pin_ok and clock_ok and payload_ok,pin_range_v=[float(pins.min()),float(pins.max())],
        receiver_transport=transport,clock_valid_widths=widths,decoded=decoded,expected=expected,payload_matches=matches,
        raw_setup_min_ps=min(setup) if setup else None,raw_hold_min_ps=min(hold) if hold else None,
        sampling_margin_qualified=False,training_cycles_qualified=False)


def prepare(replay):
    if engine()!='ngspice' or not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):raise ValueError('Use audited native replay in pinned ngspice environment')
    m=json.loads((replay/'manifest.json').read_text());i=m['identity'];layout=ROOT/i['layout']
    if i.get('tia_restore_variant')!='tia_r2':raise ValueError('Screen original TIA r2 baseline first')
    for n,h in i['inputs'].items():
        if sha(ROOT/n)!=h:raise ValueError('Native receiver input changed')
    for n,h in i['code'].items():
        if sha(ROOT/'scripts'/n)!=h:raise ValueError('Native receiver producer changed')
    if sha(replay/'library.spice')!=m['library_sha256']:raise ValueError('Native library changed')
    info=json.loads((layout/'extraction.json').read_text());audited(layout,info)
    if text_block((replay/'library.spice').read_text(),TOP)!=text_block(checked_netlist(info),TOP):raise ValueError('Native model differs from audited extraction')
    source=layout/'candidate.spice';ports,devices=flatten(circuits(source.read_text()),TOP)
    source_model=schematic_text(TOP,ports,devices)
    paths=[replay/'manifest.json',replay/'library.spice',replay/'sharp_control/bench.cir',ROOT/'requirements.json',ROOT/'receiver_acceptance.json',source]
    identity=dict(replay=str(replay.relative_to(ROOT)),layout=str(layout.relative_to(ROOT)),
        inputs=dict(i['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}),
        code=dict(i['code'],**{n:sha(ROOT/'scripts'/n) for n in CODE}),simulator=provenance(),
        scope='Three SS40 loaded native 80 ns synthetic LVDS screens and 30 source/native wide-static PVT cases. Legacy replay remains a diagnostic. No long-training, aperture or PHY release admission.')
    out=ROOT/'build/diagnostics/receiver_spec_screen'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    tasks=[]
    for task in cases(json.loads((ROOT/'requirements.json').read_text())):
        folder=out/task['id'];folder.mkdir(exist_ok=True);lib=(replay/'library.spice').read_text()
        if task['view']=='schematic':lib=replace(lib,TOP,source_model)
        deck,stop=fixture((replay/'sharp_control/bench.cir').read_text(),folder,task,lib)
        for n,body in [('library.spice',lib),('bench.cir',deck)]:
            p=folder/n
            if p.exists() and p.read_text()!=body:raise ValueError('Prepared screen changed')
            if not p.exists():p.write_text(body)
        tasks.append(dict(task,stop_ns=stop,files={n:sha(folder/n) for n in ['library.spice','bench.cir']}))
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def run(out,jobs=2):
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_spec_screen'):raise ValueError('Use prepared specification screen')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    expected=cases(json.loads((ROOT/'requirements.json').read_text()))
    if [{k:v for k,v in t.items() if k not in ['files','stop_ns']} for t in m['tasks']]!=expected:raise ValueError('Incomplete specification screen coverage')
    def unchanged():
        if out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or sha(out/'manifest.json')!=stamp or provenance()!=i['simulator']:raise ValueError('Screen identity/runtime changed')
        if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Screen input/producer changed')
    def execute(task):
        folder=out/task['id'];unchanged()
        if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Screen fixture changed')
        cached=json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
        if cached is None:
            if any((folder/n).exists() for n in ['bench.raw','ngspice.log','bench.cir.prn']):raise ValueError('Partial screen output retained; use fresh context')
            atomic(folder/'state.json',dict(status='waiting_for_slot'))
            with lease(ROOT,priority=1 if task['test']=='rate' else 0,label='receiver_spec_'+task['id']):
                unchanged();atomic(folder/'state.json',dict(status='running'))
                p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(p.stdout+p.stderr)
            if p.returncode:
                result=dict(task=task['id'],passed=False,electrical_verdict=None,numerical_or_export_failure=True,qualified_phy=False,manifest_sha256=stamp,
                    files={n:sha(folder/n) for n in ['bench.raw','ngspice.log','console.log'] if (folder/n).exists()})
                capture_manifest(folder/'summary.json',result);atomic(folder/'state.json',dict(status='failed',electrical_verdict=None));return result
        elif cached.get('numerical_or_export_failure'):
            if any(sha(folder/n)!=h for n,h in cached['files'].items()):raise ValueError('Failed screen output changed')
            return cached
        w,h=read_wave(folder/'bench.cir.prn');result=dict(task=task['id'],**measure(w,h,task),waveform_sha256=sha(folder/'bench.cir.prn'),manifest_sha256=stamp,qualified_phy=False)
        if cached is not None and result!=cached:raise ValueError('Screen cached measurement changed')
        capture_manifest(folder/'summary.json',result);atomic(folder/'state.json',dict(status='completed',passed=result['passed']));return result
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(execute,m['tasks']))
        unchanged();capture_manifest(out/'summary.json',dict(results=results,passed=all(r['passed'] for r in results),required=33,
            manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_screen',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--jobs',type=int,choices=[1,2,3],default=2);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve(),a.jobs)
