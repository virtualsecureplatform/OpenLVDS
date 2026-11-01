#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Resume unchanged scientific producers with a captured kernel-blocking lease policy."""
import argparse
from contextlib import contextmanager,nullcontext
import fcntl
import hashlib
import importlib
import json
from pathlib import Path
from threading import RLock,get_ident

from rx_candidate_aperture import lease
from spice_slots import reserved_slots

ROOT=Path(__file__).resolve().parents[1]
# Entry module, module owning its imported slot function, artifact kind,
# and whether the producer is serial and may retain one lease for the batch.
PROFILES={
    'receiver-source':('receiver_tail_timestep_retry','receiver_clamp_experiment','receiver_clamp',False),
    'receiver-dc':('receiver_tail_headroom_matrix','receiver_tail_headroom_static','receiver_tail_headroom_matrix',True),
    'driver-native':('probe_native_driver_restore','probe_native_driver_restore','driver_native_restore',False),
    'receiver-native':('probe_receiver_tail_headroom_candidate','probe_receiver_tail_headroom_candidate','receiver_replay',False),
}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def allocation(target,slots,retain=False,observe=lambda *args:None):
    slots=list(slots)
    if not slots or any(type(i) is not int or i not in range(reserved_slots(),6) for i in slots):
        raise ValueError('Select unreserved slots inside the existing six-slot budget')
    if retain and len(slots)!=1:raise ValueError('A serial retained lease needs one selected slot')
    original=target.slot;mutex=RLock();counter=0
    @contextmanager
    def selected():
        nonlocal counter
        with mutex:
            index=slots[counter%len(slots)];counter+=1
        observe('waiting_for_slot',get_ident(),index)
        try:
            with lease(index):
                observe('holding_slot',get_ident(),index)
                yield
        finally:observe('released_slot',get_ident(),index)
    try:
        if retain:
            # The matrix is serial. Its actual simulations share this one real
            # lease; no parallel producer may use this retained-batch path.
            with selected():
                target.slot=lambda:nullcontext()
                yield
        else:
            target.slot=selected
            yield
    finally:target.slot=original


def run(profile,root,slots):
    entry_name,target_name,kind,retain=PROFILES[profile]
    if not root.is_relative_to(ROOT/'build/diagnostics'/kind):raise ValueError('Unexpected scheduling artifact')
    entry=importlib.import_module(entry_name);target=importlib.import_module(target_name)
    manifest=json.loads((root/'manifest.json').read_text())
    if any(digest(ROOT/'scripts'/name)!=stamp for name,stamp in manifest['identity'].get('code',{}).items()):
        raise ValueError('Original scientific producer changed')
    names=set(manifest['identity'].get('code',{}))|{Path(__file__).name,entry_name+'.py',target_name+'.py',
        'rx_candidate_aperture.py','spice_slots.py'}
    identity=dict(profile=profile,artifact=str(root.relative_to(ROOT)),selected_slots=slots,
        retained_serial_lease=retain,global_slot_budget=6,manifest_sha256=digest(root/'manifest.json'),
        code={name:digest(ROOT/'scripts'/name) for name in sorted(names)})
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    folder=root/'execution_scheduling'/fingerprint;folder.mkdir(parents=True,exist_ok=True)
    mutex=RLock();active={}
    def save(status,**fields):
        with mutex:
            value=dict(status=status,scheduling_only=True,qualified_phy=False,active_leases=dict(active),**fields)
            path=folder/'state.json';temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)
    def unchanged():
        if digest(root/'manifest.json')!=identity['manifest_sha256'] or any(
                digest(ROOT/'scripts'/name)!=stamp for name,stamp in identity['code'].items()):
            raise ValueError('Original scientific producer or scheduling context changed')
    def observe(status,thread,index):
        unchanged()
        with mutex:
            if status=='released_slot':active.pop(str(thread),None)
            else:active[str(thread)]=dict(status=status,slot=index)
            save('running_original_producer')
    with (folder/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        capture=folder/'manifest.json'
        if capture.exists():
            if json.loads(capture.read_text())!=identity:raise ValueError('Scheduling receipt changed')
        else:capture.write_text(json.dumps(identity,indent=2)+'\n')
        try:
            unchanged();save('waiting_to_resume_original_producer')
            with allocation(target,slots,retain,observe):entry.run(root)
            unchanged();save('original_producer_completed')
        except Exception as error:
            save('held_for_diagnosis',error=str(error));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile',choices=PROFILES)
    parser.add_argument('artifact',type=Path)
    parser.add_argument('--wait-slot',type=int,choices=range(6),action='append',required=True)
    args=parser.parse_args();run(args.profile,args.artifact.resolve(),args.wait_slot)
