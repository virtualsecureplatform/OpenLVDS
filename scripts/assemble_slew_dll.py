#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind an audited physical frontend PFD to the retained 16 pF native DLL.

Only PFD definitions change. This assembles a diagnostic model and receiving
gate observations; every electrical, stability and PHY gate remains open.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import extract_slew_pfd as extraction
import pfd_native_clock_observations as clocks
from spice_library import checked_netlist, replace
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'dll_slew_native_model'
sha = extraction.sha
PUBLIC = 'REF FB RESET_N PD_ENABLE UP DN VDDD VSS'.split()


def compose(reference, physical, ports):
    if len(ports) != 8 or set(ports) != extraction.PORTS: raise ValueError('Physical PFD public interface changed')
    header = re.findall(r'(?im)^\.subckt\s+lvds_pfd\s+([^\n]*(?:\n\+[^\n]*)*)', physical)
    if len(header) != 1 or header[0].replace('\n+', ' ').split() != ports: raise ValueError('Physical PFD header differs from RC metadata')
    expected = re.findall(r'(?im)^\.subckt\s+lvds_pfd\s+([^\n]*(?:\n\+[^\n]*)*)', reference)
    if len(expected) != 1 or expected[0].replace('\n+', ' ').split() != PUBLIC: raise ValueError('Retained DLL PFD wrapper changed')
    blocks = list(re.finditer(r'(?ims)^\.subckt\s+lvds_pfd\b.*?^\.ends[^\n]*', physical))
    if len(blocks) != 1: raise ValueError('Require one flattened physical PFD definition')
    outside = physical[:blocks[0].start()] + physical[blocks[0].end():]
    if any(line.strip() and not line.lstrip().startswith('*') for line in outside.splitlines()):
        raise ValueError('Unexpected definitions or directives outside the physical PFD')
    body = re.sub(r'(?im)^(\.subckt\s+)lvds_pfd\b', r'\1lvds_pfd_physical', blocks[0][0].strip())
    body = re.sub(r'(?im)^(\.ends\s+)lvds_pfd\b', r'\1lvds_pfd_physical', body)
    mapping = dict(VGND='VSS', VPWR='VDDD')
    adapter = '.subckt lvds_pfd ' + ' '.join(PUBLIC) + '\nXPHYS ' + ' '.join(mapping.get(p, p) for p in ports) + ' lvds_pfd_physical\n.ends lvds_pfd'
    model = replace(replace(reference, 'lvds_pfd_physical', body), 'lvds_pfd', adapter)
    mask = lambda text: replace(replace(text, 'lvds_pfd_physical', 'PHYSICAL_PFD_PLACEHOLDER'), 'lvds_pfd', 'PFD_WRAPPER_PLACEHOLDER')
    if mask(model) != mask(reference): raise ValueError('Native assembly changed a definition outside the PFD')
    return model


def scientific(script, argument, input_text=None):
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    p = subprocess.run(['/usr/bin/python3', '-c', script, str(argument)], cwd=ROOT,
                       env=env, input=input_text, capture_output=True, text=True)
    if p.returncode: raise ValueError('Scientific native-model validation failed: ' + p.stderr[-2000:])
    return json.loads(p.stdout)


def reference_gate(qualification):
    if not qualification.is_relative_to(ROOT / 'build/diagnostics/dll_qualification'): raise ValueError('Require the retained corrected-DLL model context')
    return scientific('''import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'scripts')
import preflight_compensated_dll as p
q=Path(sys.argv[1]);text=p.dll_context(q);m=json.loads((q/'manifest.json').read_text());a=json.loads((q/'storage_source_admission.json').read_text())
paths=[q/n for n in ['manifest.json','storage_source_admission.json','full.spice']]
inputs=dict(m['identity']['full_models']['physical_reports']);inputs.update(a['proofs']);inputs.update({str(f.relative_to(p.ROOT)):p.sha(f) for f in paths})
code=dict(m['identity']['code']);code['preflight_compensated_dll.py']=p.sha(Path(p.__file__))
print(json.dumps(dict(inputs=inputs,code=code,full_models=m['identity']['full_models'],library_sha256=hashlib.sha256(text.encode()).hexdigest())))
''', qualification)


def bias_count(model):
    r = scientific('''import sys,json
sys.path.insert(0,'scripts')
from dll_campaign import bias_reference_count
text=sys.stdin.read();deck='XL CLK RST EN P0 P90 P180 P270 FB BAD UP DN VR PB VA VD 0 openlvds_dll'
print(json.dumps(dict(references=bias_reference_count(deck,text))))
''', 'native_model', model)
    if r['references'] != 1: raise ValueError('Assembled DLL duplicates its endpoint bias generator')
    return r['references']


def model_and_observations(identity):
    rc = ROOT / identity['rc']; report = json.loads((rc / 'strict_summary.json').read_text()); info = report['model']
    pm = json.loads((ROOT / identity['physical'] / 'summary.json').read_text())
    model = compose((ROOT / identity['qualification_reference'] / 'full.spice').read_text(), checked_netlist(info), info['ports'])
    paths = identity['observation_inputs']
    observed = clocks.derive((ROOT / paths['definition']).read_text(), Path(paths['lef']).read_text(),
                            (ROOT / paths['ext']).read_text(), (ROOT / paths['resistive_ext']).read_text(), checked_netlist(info))
    phase = clocks.probes(observed, 'XP:XPHYS:'); loop = clocks.probes(observed, 'XL:XCORE:XPFD:XPHYS:')
    network = ProbeNetwork(model)
    network.validate('XP REF FDB RST VDDD UP DN VDDD 0 lvds_pfd', phase.values())
    network.validate('XL CLK RST EN P0 P90 P180 P270 FB BAD UP DN VR PB VA VD 0 openlvds_dll', loop.values())
    return model, dict(observed, phase_probes=phase, loop_probes=loop)


def prepare(rc, qualification):
    r = extraction.verify(rc)
    if r['passed'] is not True: raise ValueError('Require complete strict native PFD RC/LVS evidence')
    rm = extraction.bound(rc); reference = reference_gate(qualification)
    if sha(qualification / 'full.spice') != reference['library_sha256']: raise ValueError('Retained DLL model changed after validation')
    parent = ROOT / rm['identity']['parent']; pm = json.loads((parent / 'manifest.json').read_text())
    pr = json.loads((parent / 'summary.json').read_text()); info = r['model']; folder = (ROOT / info['raw_netlist']).parent
    lef = Path(rm['identity']['pdk_files']['cells']).parent.parent / 'lef/sky130_fd_sc_hd.lef'
    observation_inputs = dict(definition=str(Path(pr['run']) / 'final/def/lvds_pfd.def'), lef=str(lef),
                              ext=str((folder / 'lvds_pfd_rcx.ext').relative_to(ROOT)),
                              resistive_ext=str((folder / 'lvds_pfd_rcx.res.ext').relative_to(ROOT)))
    inputs = dict(rm['identity']['inputs']); inputs.update(reference['inputs']); inputs.update(r['files'])
    inputs.update({str((rc / n).relative_to(ROOT)): sha(rc / n) for n in ('manifest.json', 'strict_summary.json')})
    code = dict(rm['identity']['code']); code.update(reference['code'])
    for n in (Path(__file__).name, 'pfd_native_clock_observations.py', 'spice_probes.py'):
        code[n] = sha(ROOT / 'scripts' / n)
    collateral = dict(rm['identity']['collateral']); collateral[str(lef)] = sha(lef)
    identity = dict(rc=str(rc.relative_to(ROOT)), physical=str(parent.relative_to(ROOT)),
                    qualification_reference=str(qualification.relative_to(ROOT)), observation_inputs=observation_inputs,
                    variant=pm['identity']['variant'], coverage_recipe=pm['identity']['coverage_recipe'],
                    analog_observation_nodes=reference['full_models']['observation_nodes'],
                    inputs=inputs, code=code, collateral=collateral,
                    scope='Only the physical PFD and its public wrapper replaced in the retained native 16 pF DLL/bias model. Actual receiving MOS gate observations. No electrical qualification transfers; all native phase/loop/stability/PHY gates remain required.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        model, observed = model_and_observations(identity); count = bias_count(model)
        files = {'full.spice': model, 'clock_observations.json': json.dumps(observed, indent=2) + '\n'}
        for n, text in files.items(): extraction.physical.write_once(out / n, text)
        (out / 'producers').mkdir(exist_ok=True)
        for n in code: extraction.physical.write_once(out / 'producers' / n, (ROOT / 'scripts' / n).read_text())
        extraction.physical.capture_manifest(out / 'manifest.json', dict(identity=identity, endpoint_bias_references=count,
                   files={n: sha(out / n) for n in files}, qualified_phy=False, physical_admission=False))
    return out


def verify(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE) or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
            m['qualified_phy'] is not False or m['physical_admission'] is not False or m['endpoint_bias_references'] != 1 or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items()) or
            any(sha(Path(n)) != h for n, h in i['collateral'].items()) or
            set(m['files']) != {'full.spice', 'clock_observations.json'} or any(sha(out / n) != h for n, h in m['files'].items())):
        raise ValueError('Native repaired-DLL assembly changed')
    model, observed = model_and_observations(i)
    if (model != (out / 'full.spice').read_text() or observed != json.loads((out / 'clock_observations.json').read_text()) or bias_count(model) != 1):
        raise ValueError('Native repaired-DLL geometry, probes or bias changed')
    return m


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'verify']); p.add_argument('artifact', type=Path); p.add_argument('--qualification', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        if not a.qualification: p.error('--qualification required')
        result = prepare(a.artifact.resolve(), a.qualification.resolve())
    else: result = verify(a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
