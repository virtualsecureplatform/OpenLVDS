#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Wait for native receiver replay, then run its prepared component/link checks."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def admitted(summary):
    results=summary.get('results',[])
    if not summary.get('diagnostic_complete') or len(results)!=2 or {r['task'] for r in results}!={'captured','sharp_control'}:
        raise ValueError('Incomplete native receiver replay')
    for result in results:
        transport=result['receiver_transport'];pulses=transport['pulses']
        if transport['missing_output_edges'] or not pulses or any(p['output_edges_in_next_input_period']!=1 for p in pulses):
            raise ValueError('Native receiver loses or repeats clock edges')


def selected(replay,components,link,root=ROOT):
    native=json.loads((replay/'manifest.json').read_text())['identity']
    component=json.loads((components/'manifest.json').read_text())['identity']
    full_link=json.loads((link/'manifest.json').read_text())['identity']
    if (component['replay']!=str(replay.relative_to(root)) or full_link['replay']!=str(replay.relative_to(root)) or
        component['layout']!=native['layout'] or full_link['receiver']!=native['layout']):
        raise ValueError('Follow-up artifacts select different receiver models or replays')
    return native,component,full_link


def run(replay,components,link,producer_unit):
    for path,kind in [(replay,'receiver_replay'),(components,'receiver_components'),(link,'receiver_candidate_link')]:
        if not path.is_relative_to(ROOT/'build/diagnostics'/kind):raise ValueError('Use isolated receiver follow-up artifacts')
    identities=selected(replay,components,link)
    code=set().union(*(set(i['code']) for i in identities))|{Path(__file__).name}
    identity=dict(manifests={str((p/'manifest.json').relative_to(ROOT)):digest(p/'manifest.json') for p in [replay,components,link]},
                  code={n:digest(ROOT/'scripts'/n) for n in code},producer_unit=producer_unit)
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    folder=replay/'followup'/fingerprint;folder.mkdir(parents=True,exist_ok=True)
    def save(status,**fields):
        (folder/'state.json.tmp').write_text(json.dumps(dict(status=status,qualified_phy=False,**fields),indent=2)+'\n')
        (folder/'state.json.tmp').replace(folder/'state.json')
    def unchanged():
        if any(digest(ROOT/n)!=v for n,v in identity['manifests'].items()) or any(digest(ROOT/'scripts'/n)!=v for n,v in identity['code'].items()):
            raise ValueError('Receiver follow-up context changed')
    def execute(item):
        label,script,args,artifact=item;unchanged()
        with (folder/(label+'.log')).open('w') as output:
            process=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','python3','scripts/'+script]+args,
                                   cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        unchanged();process.check_returncode()
        report=artifact/'summary.json';result=json.loads(report.read_text())
        if result['manifest_sha256']!=digest(artifact/'manifest.json'):
            raise ValueError('Follow-up report belongs to another manifest')
        return label,dict(passed=result['passed'],report=str(report.relative_to(ROOT)),sha256=digest(report))
    with (replay/'.receiver_followup.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        capture=folder/'manifest.json'
        if capture.exists() and json.loads(capture.read_text())!=identity:raise ValueError('Follow-up identity changed')
        capture.write_text(json.dumps(identity,indent=2)+'\n')
        (folder/'producer.py').write_bytes(Path(__file__).read_bytes())
        try:
            while True:
                unchanged()
                try:
                    state=subprocess.run(['systemctl','--user','show',producer_unit,'-p','ActiveState','--value'],
                                         capture_output=True,text=True,check=True).stdout.strip()
                except (OSError,subprocess.CalledProcessError):
                    save('retrying_native_owner_observation');time.sleep(10);continue
                if state not in ['active','activating']:
                    if not (replay/'summary.json').exists():raise ValueError('Native replay owner ended without a complete report')
                    admitted(json.loads((replay/'summary.json').read_text()));break
                save('waiting_for_native_replay',owner_state=state);time.sleep(10)
            # The children independently remeasure both actual native traces
            # through the selected replay verifier before acquiring SPICE slots.
            save('running_component_and_link_diagnostics')
            items=[('components','qualify_receiver_components.py',
                    ['run',str(components.relative_to(ROOT)),'--jobs','3'],components),
                   ('link','probe_receiver_candidate_link.py',['run',str(link.relative_to(ROOT))],link)]
            results={}
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures={pool.submit(execute,item):item[0] for item in items}
                for future in as_completed(futures):
                    label=futures[future]
                    try:_,results[label]=future.result()
                    except Exception as error:results[label]=dict(passed=False,error=str(error))
                    save('running_component_and_link_diagnostics',results=results)
            unchanged()
            save('diagnostics_passed' if all(r['passed'] for r in results.values()) else 'held_for_diagnosis',
                 results=results,next_gate='Complete native DLL/model/aperture/RC/headroom/full-link release qualification')
        except Exception as error:
            save('held_for_diagnosis',error=str(error));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay',type=Path);p.add_argument('components',type=Path);p.add_argument('link',type=Path)
    p.add_argument('--producer-unit',required=True);a=p.parse_args()
    run(a.replay.resolve(),a.components.resolve(),a.link.resolve(),a.producer_unit)
