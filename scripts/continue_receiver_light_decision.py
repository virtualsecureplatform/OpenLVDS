#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Continue the original-decision source experiment through audited native replay."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
PRODUCERS=['continue_receiver_light_decision.py','layout_receiver_light_decision_candidate.py',
           'probe_receiver_light_decision_candidate.py','receiver_candidate_rc.py',
           'extract.py','audit_rc.py','physical_policy.py','continue_receiver_candidate.py','continue_receiver_wide_input.py']


from continue_receiver_wide_input import digest,artifact,source_finished


def run(screen,parent,unit):
    screen=artifact(str(screen),'receiver_clamp');parent=artifact(str(parent),'clock_restore')
    source=json.loads((screen/'manifest.json').read_text())['identity']
    if source['parent']!=str(parent.relative_to(ROOT)):
        raise ValueError('Replay parent differs from the source comparison')
    # Freeze every downstream scientific producer, including transitive native
    # replay dependencies, without importing numerical modules on the host.
    import ast
    native=ast.parse((ROOT/'scripts/probe_receiver_light_decision_candidate.py').read_text())
    code=next(ast.literal_eval(n.value) for n in native.body if isinstance(n,ast.Assign) and
              any(isinstance(t,ast.Name) and t.id=='CODE' for t in n.targets))
    names=set(code)|set(source['code'])|set(PRODUCERS)
    identity=dict(code={n:digest(ROOT/'scripts'/n) for n in names},source_unit=unit,
        manifests={str((p/'manifest.json').relative_to(ROOT)):digest(p/'manifest.json') for p in [screen,parent]})
    folder=screen/'native_continuation';folder.mkdir(exist_ok=True)
    def save(status,**fields):
        path=folder/'state.json';temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(status=status,qualified_phy=False,**fields),indent=2)+'\n');temp.replace(path)
    def unchanged():
        if any(digest(ROOT/'scripts'/n)!=v for n,v in identity['code'].items()) or any(
                digest(ROOT/n)!=v for n,v in identity['manifests'].items()):
            raise ValueError('Original-decision continuation context changed')
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
                try:
                    result=subprocess.run(['systemctl','--user','show',unit,'-p','LoadState','-p','ActiveState',
                        '-p','Result','-p','ExecMainStatus'],capture_output=True,text=True,check=True)
                except (OSError,subprocess.CalledProcessError):
                    save('retrying_source_owner_observation');time.sleep(10);continue
                observation=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
                complete=all((screen/n/'summary.json').exists() for n in
                             ['unclamped_captured','clamped_captured','clamped_sharp_control']) and (screen/'summary.json').exists()
                if source_finished(observation,complete):break
                save('waiting_for_source_comparison',owner=observation);time.sleep(10)
            # Layout repeats the exact source and one-to-one waveform gates.
            result=json.loads(execute('layout',['--tools','--ngspice','/usr/bin/python3',
                'scripts/layout_receiver_light_decision_candidate.py',str(screen.relative_to(ROOT))]))
            if not result['passed']:raise ValueError('Original-decision physical checks failed')
            layout=artifact(result['output'],'receiver_layout')
            execute('extract',['--tools','python3','scripts/receiver_candidate_rc.py',str(layout.relative_to(ROOT))])
            replay=artifact(execute('prepare_replay',['--ngspice','python3','scripts/probe_receiver_light_decision_candidate.py',
                'prepare',str(parent.relative_to(ROOT)),str(layout.relative_to(ROOT))]),'receiver_replay')
            execute('run_replay',['--ngspice','python3','scripts/probe_receiver_light_decision_candidate.py',
                'run',str(replay.relative_to(ROOT))])
            from continue_receiver_candidate import admitted
            admitted(json.loads((replay/'summary.json').read_text()))
            save('native_replay_passed',layout=str(layout.relative_to(ROOT)),replay=str(replay.relative_to(ROOT)),
                 next_gate='Candidate components, complete RC comparisons, DLL/aperture and full link qualification')
        except Exception as error:
            save('held_for_diagnosis',error=str(error));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('screen',type=Path);p.add_argument('parent',type=Path)
    p.add_argument('--source-unit',required=True);a=p.parse_args();run(a.screen.resolve(),a.parent.resolve(),a.source_unit)
