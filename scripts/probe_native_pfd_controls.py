#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Validate reset/disable protocol against one retained matched-slew native PFD.

This is a new protocol-control experiment, not a repeated phase test or a
repair admission. It preserves the retained DLL/PFD/bias model exactly.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess

import assemble_slew_dll as assembly
import pfd_control_protocol as protocol
import pilot_native_slew_dll as phase
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='pfd_controls_baseline'
sha=assembly.sha
SPEC=dict(kind='phase',process='ss',temperature=40,mhz=400,reference_slew_ps=100,feedback_slew_ps=100,offset_ps=0)
OUTPUTS=('bench.raw','bench.cir.prn','ngspice.log','console.log')


def prepare(qualification):
    q=assembly.reference_gate(qualification);qm=json.loads((qualification/'manifest.json').read_text())
    pfd=ROOT/q['full_models']['pfd'];info=json.loads((pfd/'extraction.json').read_text());pr=json.loads((pfd/'summary.json').read_text())
    if q['full_models']['inputs']['lvds_pfd']!=info['netlist_sha256']:raise ValueError('Retained DLL uses a different native PFD')
    folder=(ROOT/info['raw_netlist']).parent;definition=ROOT/pr['run']/'final/def/lvds_pfd.def'
    lef=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef'
    ext=folder/'lvds_pfd_rcx.ext';res=folder/'lvds_pfd_rcx.res.ext'
    observed=assembly.clocks.derive(definition.read_text(),lef.read_text(),ext.read_text(),res.read_text(),(ROOT/info['netlist']).read_text())
    gate_probes=assembly.clocks.probes(observed,'XP:XPHYS:')
    template_path=qualification/'phase_ss_40_0ps/bench.cir';donor=next(t for t in qm['tasks'] if t['id']==template_path.parent.name)
    if sha(template_path)!=donor['deck_sha256']:raise ValueError('Native matched-slew donor fixture changed')
    inputs=dict(q['inputs']);paths=[pfd/'summary.json',pfd/'extraction.json',definition,ext,res,ROOT/info['netlist'],template_path]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(q['code'])
    for n in (Path(__file__).name,'pfd_control_protocol.py','pfd_native_clock_observations.py','pilot_native_slew_dll.py','assemble_slew_dll.py',
              'extract_slew_pfd.py','harden_slew_pfd.py','slew_pfd_floorplan.py','pfd_slew_policy.py','probe_dll_input_conditioning.py',
              'spice_dispatch.py','run_ngspice.py','spice_probes.py','receiver_static_diagnosis.py'):
        code[n]=sha(ROOT/'scripts'/n)
    model=(qualification/'full.spice').read_text();template=template_path.read_text()
    prefix=template[:template.index('XB PB NB VDDIO 0 lvds_bias')]
    placeholder='__PFD_CONTROL_MODEL__'
    deck,aliases=phase.fixture(SPEC,q['full_models']['observation_nodes'],gate_probes,prefix,placeholder,model)
    deck=protocol.apply(deck);aliases.update(RST='RST',ENABLE='ENABLE')
    ProbeNetwork(model).validate(deck,aliases.values())
    identity=dict(qualification=str(qualification.relative_to(ROOT)),spec=SPEC,protocol=protocol.VERSION,inputs=inputs,code=code,
                  lef=dict(path=str(lef),sha256=sha(lef)),simulator=provenance(),
                  aliases=aliases,normalized_fixture_sha256=hashlib.sha256(deck.encode()).hexdigest(),
                  scope='One new SS40/400 MHz 100/100 ps matched-slew protocol baseline. Original native DLL/PFD/bias, continuously running clocks, observed RST/ENABLE, cleared UP/DN and recovered phase health. No candidate, timing-repair, full-PVT or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);deck=deck.replace(placeholder,str(out/'full.spice'))
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        (out/'producers').mkdir(exist_ok=True)
        for n,text in [('full.spice',model),('bench.cir',deck)]:assembly.extraction.physical.write_once(out/n,text)
        for n in code:assembly.extraction.physical.write_once(out/'producers'/n,(ROOT/'scripts'/n).read_text())
        capture_manifest(out/'manifest.json',dict(identity=identity,aliases=aliases,
            files={n:sha(out/n) for n in ('full.spice','bench.cir')},qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
        out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
        i['spec']!=SPEC or i['protocol']!=protocol.VERSION or i['simulator']!=provenance() or
        m['qualified_phy'] is not False or m['aliases']!=i['aliases'] or set(m['files'])!={'full.spice','bench.cir'} or
        any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
        any(sha(ROOT/'scripts'/n)!=h or sha(out/'producers'/n)!=h for n,h in i['code'].items()) or
        sha(Path(i['lef']['path']))!=i['lef']['sha256'] or any(sha(out/n)!=h for n,h in m['files'].items()) or
        (out/'full.spice').read_bytes()!=(ROOT/i['qualification']/'full.spice').read_bytes()):
        raise ValueError('PFD protocol baseline context changed')
    normalized=(out/'bench.cir').read_text().replace(str(out/'full.spice'),'__PFD_CONTROL_MODEL__')
    if hashlib.sha256(normalized.encode()).hexdigest()!=i['normalized_fixture_sha256']:raise ValueError('Protocol stimulus or observation binding changed')
    return m


def measure(out,m):
    task=dict(spec=SPEC,aliases=m['aliases']);original=phase.measure(out,task)
    wave,header=phase.original.completed(out)
    for alias,node in m['aliases'].items():header['V('+alias+')']=header['V('+node.upper()+')']
    clock_names=['REF','FDB']+[n for n in m['aliases'] if n.startswith(('REF_FF_CLK_','FB_FF_CLK_'))]
    controls=protocol.measure(wave,header,400,clock_names)
    return dict(baseline_protocol_passed=bool(original['passed'] and controls['passed']),phase=original,controls=controls,
                repair_admission=False,physical_admission=False,qualified_phy=False)


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if any((out/n).exists() for n in (*OUTPUTS,'state.json','summary.json')):raise ValueError('Existing/partial protocol baseline retained; no retry')
        try:
            atomic(out/'state.json',dict(status='running_protocol_baseline',qualified_phy=False))
            with lease(ROOT,priority=2,label='pfd_reset_enable_baseline'):
                bound(out);p=subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
            (out/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();bound(out)
            if sha(out/'manifest.json')!=stamp:raise ValueError('PFD protocol manifest changed')
            report=dict(measure(out,m),manifest_sha256=stamp,files={n:sha(out/n) for n in OUTPUTS})
            capture_manifest(out/'summary.json',report)
            atomic(out/'state.json',dict(status='protocol_baseline_passed' if report['baseline_protocol_passed'] else 'held_protocol_baseline_failed',qualified_phy=False))
            return report
        except Exception as e:
            atomic(out/'state.json',dict(status='held_for_diagnosis',error=str(e),qualified_phy=False));raise


def verify(out):
    m=bound(out);r=json.loads((out/'summary.json').read_text())
    expected=dict(measure(out,m),manifest_sha256=sha(out/'manifest.json'),files={n:sha(out/n) for n in OUTPUTS})
    if r!=expected:raise ValueError('PFD protocol baseline evidence changed')
    bound(out);return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path)
    a=p.parse_args();r=globals()[a.action](a.artifact.resolve());print(r if a.action=='prepare' else json.dumps(r,indent=2),flush=True)
