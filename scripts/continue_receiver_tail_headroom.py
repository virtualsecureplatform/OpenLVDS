#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Continue reduced decision-tail receiver through full DC/source gates and native replay."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
PRODUCERS=['continue_receiver_tail_headroom.py','layout_receiver_tail_headroom_candidate.py',
           'probe_receiver_tail_headroom_candidate.py','receiver_candidate_rc.py',
           'run_spice_wait_slot.py','rx_candidate_aperture.py',
           'extract.py','audit_rc.py','physical_policy.py','continue_receiver_candidate.py','continue_receiver_wide_input.py']


from continue_receiver_wide_input import digest,artifact,source_finished


def replay_command(replay,wait_slots):
    if any(type(slot) is not int or slot not in range(6) for slot in wait_slots):
        raise ValueError('Native wait slots must remain inside the six-slot budget')
    if not wait_slots:
        return ['--ngspice','python3','scripts/probe_receiver_tail_headroom_candidate.py','run',str(replay)]
    return ['--ngspice','python3','scripts/run_spice_wait_slot.py','receiver-native',str(replay)]+[
        item for slot in wait_slots for item in ['--wait-slot',str(slot)]]


def run(screen,parent,unit,static_screen,dc_unit,native_wait_slots=None):
    native_wait_slots=list(native_wait_slots or [])
    replay_command(Path('unused'),native_wait_slots)  # Validate before capturing any owner.
    screen=artifact(str(screen),'receiver_clamp');parent=artifact(str(parent),'clock_restore')
    static_screen=artifact(str(static_screen),'receiver_tail_headroom_matrix')
    static_identity=json.loads((static_screen/'manifest.json').read_text())['identity']
    source=json.loads((screen/'manifest.json').read_text())['identity']
    if source['parent']!=str(parent.relative_to(ROOT)):
        raise ValueError('Replay parent differs from the source comparison')
    # Freeze every downstream scientific producer, including transitive native
    # replay dependencies, without importing numerical modules on the host.
    import ast
    native=ast.parse((ROOT/'scripts/probe_receiver_tail_headroom_candidate.py').read_text())
    code=next(ast.literal_eval(n.value) for n in native.body if isinstance(n,ast.Assign) and
              any(isinstance(t,ast.Name) and t.id=='CODE' for t in n.targets))
    children=[ROOT/child['root'] for child in static_identity['children']]
    static_code={name for child in children for name in json.loads((child/'manifest.json').read_text())['identity']['code']}
    names=set(code)|set(source['code'])|static_code|set(PRODUCERS)
    identity=dict(code={n:digest(ROOT/'scripts'/n) for n in names},source_unit=unit,dc_unit=dc_unit,native_wait_slots=native_wait_slots,
        manifests={str((p/'manifest.json').relative_to(ROOT)):digest(p/'manifest.json') for p in [screen,parent,static_screen]+children})
    folder=screen/'native_continuation';folder.mkdir(exist_ok=True)
    def save(status,**fields):
        path=folder/'state.json';temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(status=status,qualified_phy=False,**fields),indent=2)+'\n');temp.replace(path)
    def unchanged():
        if any(digest(ROOT/'scripts'/n)!=v for n,v in identity['code'].items()) or any(
                digest(ROOT/n)!=v for n,v in identity['manifests'].items()):
            raise ValueError('stronger-restoration continuation context changed')
    def execute(label,args):
        unchanged();save(label)
        path=folder/(label+'.log')
        with path.open('w') as output:
            process=subprocess.run([str(ROOT/'scripts/env.sh')]+args,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        process.check_returncode();unchanged()
        return path.read_text().strip().splitlines()[-1]
    with (folder/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        capture=folder/'manifest.json'
        if capture.exists() and json.loads(capture.read_text())!=identity:raise ValueError('Continuation identity changed')
        capture.write_text(json.dumps(identity,indent=2)+'\n')
        (folder/'producer.py').write_bytes(Path(__file__).read_bytes())
        try:
            while True:
                unchanged()
                source_complete=all((screen/n/'summary.json').exists() for n in
                    ['unclamped_captured','clamped_captured','clamped_sharp_control']) and (screen/'summary.json').exists()
                dc_complete=(static_screen/'summary.json').exists() and all((child/'summary.json').exists() for child in children)
                owners={};finished=[]
                try:
                    for owner,complete in [(unit,source_complete),(dc_unit,dc_complete)]:
                        result=subprocess.run(['systemctl','--user','show',owner,'-p','LoadState','-p','ActiveState',
                            '-p','Result','-p','ExecMainStatus'],capture_output=True,text=True,check=True)
                        observation=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
                        owners[owner]=observation
                        finished.append(source_finished(observation,complete))
                except (OSError,subprocess.CalledProcessError):
                    save('retrying_upstream_owner_observation');time.sleep(10);continue
                if all(finished):break
                save('waiting_for_source_and_full_dc',owners=owners);time.sleep(10)
            # Layout repeats the exact source and one-to-one waveform gates.
            result=json.loads(execute('layout',['--tools','--ngspice','/usr/bin/python3',
                'scripts/layout_receiver_tail_headroom_candidate.py',str(screen.relative_to(ROOT)),
                '--dc-matrix',str(static_screen.relative_to(ROOT))]))
            if not result['passed']:raise ValueError('stronger-restoration physical checks failed')
            layout=artifact(result['output'],'receiver_layout')
            execute('extract',['--tools','python3','scripts/receiver_candidate_rc.py',str(layout.relative_to(ROOT))])
            replay=artifact(execute('prepare_replay',['--ngspice','python3','scripts/probe_receiver_tail_headroom_candidate.py',
                'prepare',str(parent.relative_to(ROOT)),str(layout.relative_to(ROOT))]),'receiver_replay')
            execute('run_replay',replay_command(replay.relative_to(ROOT),native_wait_slots))
            from continue_receiver_candidate import admitted
            admitted(json.loads((replay/'summary.json').read_text()))
            save('native_replay_passed',layout=str(layout.relative_to(ROOT)),replay=str(replay.relative_to(ROOT)),
                 next_gate='Candidate components, complete RC comparisons, DLL/aperture and full link qualification')
        except Exception as error:
            save('held_for_diagnosis',error=str(error));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('screen',type=Path);p.add_argument('parent',type=Path)
    p.add_argument('--dc-unit',required=True);p.add_argument('--source-unit',required=True);p.add_argument('--dc-matrix',type=Path,required=True)
    p.add_argument('--native-wait-slot',type=int,choices=range(6),action='append',default=[])
    a=p.parse_args();run(a.screen.resolve(),a.parent.resolve(),a.source_unit,a.dc_matrix.resolve(),a.dc_unit,a.native_wait_slot)
