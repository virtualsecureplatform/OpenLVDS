#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare schematic receiver decision clamping under saved pin waveforms."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
from diagnose_link_clock import pulse_transport
from dll_campaign import atomic,text_block
from dll_measurements import read_wave
from layout import circuits,flatten,schematic_text
from layout_receiver_gain_candidate import source_variant as gain_source,MID
from spice_engine import command,engine,provenance
from spice_library import replace
from spice_scope import closure_hash
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
CODE=['receiver_clamp_experiment.py','layout.py','lvs_utils.py','layout_receiver_gain_candidate.py',
      'layout_receiver_tail_candidate.py','layout_receiver_variant.py','diagnose_link_clock.py',
      'dll_campaign.py','dll_measurements.py','spice_engine.py','spice_library.py','spice_scope.py',
      'spice_probes.py','spice_slots.py','run_ngspice.py']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_variant(source,clamped=True):
    source=gain_source(source)
    if not clamped:return source
    block=text_block(source,TOP)
    if 'CO_TRACK' in block:raise ValueError('Decision clamp reference already exists')
    extra=(f'XTRACK CO_TRACK CO_TRACK VDDD VSS {MID}\n'
           'XCLAMP0 CO CO_TRACK VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=1.25\n'
           'XCLAMP1 CO CO_TRACK VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=1.25\n')
    changed=re.sub(r'(?im)^\.ends[^\n]*',lambda m:extra+m[0],block)
    return replace(source,TOP,changed)


def prepare(parent):
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/clock_restore'):
        raise ValueError('Use a captured replay in the pinned ngspice environment')
    previous=json.loads((parent/'manifest.json').read_text());baseline=(parent/'library.spice').read_text()
    if digest(parent/'library.spice')!=previous['library_sha256']:raise ValueError('Parent library changed')
    inputs=[parent/'manifest.json',parent/'library.spice',ROOT/'analog/openlvds.spice']
    inputs += [parent/t['id']/'bench.cir' for t in previous['tasks']]
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):digest(p) for p in inputs},
                  code={n:digest(ROOT/'scripts'/n) for n in CODE},simulator_provenance=provenance(),
                  scope='Schematic finger receiver comparison; native shared bias and digital RX retained; no receiver wire RC or physical qualification')
    root=ROOT/'build/diagnostics/receiver_clamp'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():return root
    root.mkdir(parents=True);tasks=[]
    for clamped,mode in [(False,'captured'),(True,'captured'),(True,'sharp_control')]:
        name=('clamped_' if clamped else 'unclamped_')+mode;out=root/name;out.mkdir()
        source=source_variant((ROOT/'analog/openlvds.spice').read_text(),clamped)
        ports,devices=flatten(circuits(source),TOP);model=schematic_text(TOP,ports,devices)
        header=re.search(r'(?im)^\.subckt[^\n]*(?:\n\+[^\n]*)*',text_block(baseline,TOP))
        if header[0].replace('\n+',' ').split()[2:]!=ports:raise ValueError('Receiver terminal order changed')
        library=replace(baseline,TOP,model)
        for protected in ['lvds_bias','openlvds_ddr_rx']:
            if closure_hash(library,protected)!=closure_hash(baseline,protected):raise ValueError('Comparison changed unrelated circuits')
        old=parent/mode/'bench.cir';task=next(t for t in previous['tasks'] if t['id']==mode)
        if digest(old)!=task['deck_sha256']:raise ValueError('Parent fixture changed')
        deck=old.read_text();include=f'.include "{parent}/library.spice"'
        if deck.count(include)!=1:raise ValueError('Ambiguous parent library binding')
        deck=deck.replace(include,f'.include "{out}/library.spice"')
        aliases={n:'XRC:'+TOP+'__'+n for n in ['PP','PN','CO']+(['CO_TRACK'] if clamped else [])}
        probes=re.search(r'(?im)^\.print tran[^\n]*',deck)
        deck=deck[:probes.end()]+' '+ ' '.join('V('+n+')' for n in aliases.values())+deck[probes.end():]
        ProbeNetwork(library).validate(deck,aliases.values())
        (out/'candidate.spice').write_text(source);(out/'library.spice').write_text(library);(out/'bench.cir').write_text(deck)
        tasks.append(dict(id=name,clamped=clamped,mode=mode,aliases=aliases,
            files={n:digest(out/n) for n in ['candidate.spice','library.spice','bench.cir']}))
    atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):raise ValueError('Use a prepared clamp experiment')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    def unchanged():
        if provenance()!=identity['simulator_provenance'] or any(digest(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()):
            raise ValueError('Clamp comparison producer changed')
        if any(digest(ROOT/p)!=h for p,h in identity['inputs'].items()):raise ValueError('Clamp comparison input changed')
        for task in manifest['tasks']:
            if any(digest(root/task['id']/n)!=h for n,h in task['files'].items()):raise ValueError('Clamp fixture changed')
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged();results=[]
        for task in manifest['tasks']:
            folder=root/task['id'];report=folder/'summary.json';cached=None
            if report.exists():
                cached=json.loads(report.read_text())
                if cached['waveform_sha256']!=digest(folder/'bench.cir.prn'):raise ValueError('Clamp waveform changed')
            else:
                atomic(folder/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
                with slot():
                    unchanged();atomic(folder/'execution.json',dict(status='running',qualified_phy=False))
                    result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
            wave,header=read_wave(folder/'bench.cir.prn');t=wave[:,1]
            if t[-1]<80e-9-1e-12:raise ValueError('Incomplete clamp comparison transient')
            keep=(t>=15e-9)&(t<=75e-9)
            def signal(name):return wave[:,header[name.upper()]]
            transport=pulse_transport(t,signal('V(RCP)')-signal('V(RCN)'),signal('V(RXCLOCK)'),15e-9,75e-9)
            observations={}
            for name,node in task['aliases'].items():
                v=signal('V('+node+')')[keep];observations[name]=dict(min_v=float(v.min()),max_v=float(v.max()))
            result=dict(task=task['id'],qualified_phy=False,qualification_verdict=None,receiver_transport=transport,
                clock_internal_node_ranges_v=observations,
                manifest_sha256=digest(root/'manifest.json'),waveform_sha256=digest(folder/'bench.cir.prn'))
            unchanged()
            if cached is not None and cached!=result:raise ValueError('Clamp cached analysis differs from waveform')
            atomic(report,result);results.append(result)
        atomic(root/'summary.json',dict(diagnostic_complete=True,qualified_phy=False,qualification_verdict=None,
            scope=identity['scope'],manifest_sha256=digest(root/'manifest.json'),results=results))
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
