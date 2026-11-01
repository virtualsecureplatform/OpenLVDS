#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the uniformly scaled decision receiver only after exact DC and clock gates."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import layout_receiver_variant as physical
from layout_receiver_monitor_after import place
from receiver_layout_reference import cached,reordered
import receiver_scaled_decision_clock as clock

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
CASES=clock.clock.CASES


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_gate(screen,static_screen):
    if not screen.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use the isolated uniform-decision source clock screen')
    required=['manifest.json','summary.json','source_clock_admission.json']
    required.extend(name+'/summary.json' for name in CASES)
    if any(not (screen/n).is_file() for n in required):
        raise ValueError('Complete all uniform-decision source clock controls before layout')
    manifest=json.loads((screen/'manifest.json').read_text());identity=manifest['identity']
    if identity.get('static_screen')!=str(static_screen.relative_to(ROOT)):
        raise ValueError('Physical static screen differs from the source clock admission')
    # Rechecking a completed source screen cannot launch a missing simulation.
    # Serialize cached consumers independently from the scientific execution lock.
    with (screen/'.cached_verification.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);clock.run(screen)
    report=json.loads((screen/'source_clock_admission.json').read_text())
    if (report.get('source_clock_passed') is not True or report.get('manifest_sha256')!=digest(screen/'manifest.json') or
            report.get('report_sha256')!=digest(screen/'summary.json')):
        raise ValueError('Uniform-decision source clock admission failed or changed')
    paths=[screen/n for n in ['manifest.json','summary.json','source_clock_admission.json']]
    paths.extend(screen/name/n for name in CASES for n in ['candidate.spice','library.spice','bench.cir','summary.json','bench.cir.prn'])
    return dict(identity['static_proofs'],**{str(p.relative_to(ROOT)):digest(p) for p in paths})


def build(screen,static_screen):
    proofs=source_gate(screen,static_screen)
    source=clock.factory.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
    source_identity=json.loads((screen/'manifest.json').read_text())['identity']
    metadata=dict(input_tail_scale=2,decision_scale=4,decision_tail_scale=1,decision_tail_width_um=64,
        decision_input_width_um=32,decision_load_width_um=32,decision_clamped=False,
        clamp_variant='unclamped_uniform_decision_scale4',clamp_reference=None,parallel_clamp_units=0,
        replica_monitor_unloaded=True,reference_widths_um=[32,16],
        first_restoration_nfet_model='sky130_fd_pr__nfet_01v8',restoration_widths_um=[[8,4],[16,8],[16,8]],
        restoration='Three inverters: P/N widths 8/4, 16/8, 16/8; unchanged final drive and overall polarity',
        placement='Six unloaded monitor devices after all functional devices; other device order retained',
        source_screen=str(screen.relative_to(ROOT)),static_screen=str(static_screen.relative_to(ROOT)),
        source_screen_proofs=proofs,source_maximum_step_ps=1)
    producers=set(source_identity['code'])|{Path(__file__).name,'layout_receiver_monitor_after.py',
        'receiver_layout_reference.py','layout_receiver_tail_headroom_candidate.py'}
    names=producers|{'layout_receiver_variant.py','layout.py','lvs_utils.py','spice_library.py'}
    identity=dict(metadata,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        code={n:digest(ROOT/'scripts'/n) for n in sorted(names)})
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ROOT/'build/diagnostics/receiver_layout'/fingerprint[:16];out.mkdir(parents=True,exist_ok=True)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=cached(out,identity,source)
        if report is not None:return out,report
        original=physical.draw_macro
        def draw(folder,top,ports,devices,library):
            if top!=TOP:raise ValueError('Receiver-only scaled-decision build')
            return original(folder,top,ports,reordered(devices,place),library)
        try:
            physical.draw_macro=draw
            actual,report=physical.build(source,metadata,producers)
        finally:physical.draw_macro=original
        if actual!=out or report['identity']!=identity:raise ValueError('Scaled-decision physical identity differs')
        paths=[out/(TOP+s) for s in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']]
        paths.extend(out/n for n in ['candidate.spice','summary.json'])
        (out/'physical_cache.json').write_text(json.dumps(dict(files={p.name:digest(p) for p in paths}),indent=2)+'\n')
    return out,report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('screen',type=Path);parser.add_argument('--dc-matrix',type=Path,required=True)
    args=parser.parse_args();out,report=build(args.screen.resolve(),args.dc_matrix.resolve())
    print(json.dumps(dict(output=str(out),passed=report['passed'])),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
