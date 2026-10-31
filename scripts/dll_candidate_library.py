# SPDX-License-Identifier: GPL-3.0-only
"""Assemble isolated, audited 15/8-terminal DLL networks by terminal name."""
import hashlib
import json
from pathlib import Path
import re

from digital_candidate_rc import captured_inputs
from dll_campaign import closure, text_block, bias_reference_count
from dll_design import ANALOG_PORTS, PFD_PORTS
from layout import circuits, flatten, schematic_text
from physical_policy import delay_cells_absent
from pfd_candidate_policy import pfd_candidate_paths_retained
from rc_fast import fast
from spice_library import checked_netlist, library, replace

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audited(out, info):
    audit = json.loads((out / 'rc_audit.json').read_text())
    if not (audit.get('passed') and audit['netlist_sha256'] == info['netlist_sha256'] and
            audit['gds_sha256'] == info['gds_sha256'] and
            audit['source_sha256'] == info['source_sha256'] and
            digest(ROOT / audit['report']) == audit['report_sha256']):
        raise ValueError('Candidate lacks a current independent RC audit')
    checked_netlist(info)
    return audit


def approximate(out, info):
    """An approximation remains explicitly unqualified until waveform comparison."""
    dest = out / 'candidate.fast_0.1ps.spice'
    record = dest.with_suffix('.json')
    metadata = json.loads(record.read_text()) if record.exists() else {}
    if (metadata.get('source_sha256') != info['netlist_sha256'] or
            not dest.exists() or metadata.get('fast_sha256') != digest(dest)):
        metadata = fast(ROOT / info['netlist'], dest, .1)
    result = dict(info, exact_sha256=info['netlist_sha256'], exact_netlist=info['netlist'],
                  netlist=str(dest.relative_to(ROOT)), netlist_sha256=metadata['fast_sha256'],
                  approximate_transient=True, qualified=False, fast_reduction=metadata)
    checked_netlist(result)
    return result


def observation_nodes(netlist):
    """Magic can split a routing label into .tN terminals during extresist.

    The capacitor plates remain actual device terminals in both the exact
    and approximate networks. Observe every storage plate rather than invent
    an alias for a routing node that no longer exists.
    """
    result = {}
    for name in ['CTRL', 'VCOPY']:
        prefix = 'openlvds_dll_analog__' + name
        candidates = []
        for line in netlist.splitlines():
            words = line.split()
            if not words or not words[0].lower().startswith('x') or 'sky130_fd_pr__cap_mim_m3_1' not in words:
                continue
            parameters = dict(word.split('=', 1) for word in words if '=' in word)
            for node in words[1:3]:
                if node == prefix or node.startswith(prefix+'.'):
                    candidates.append((-float(parameters['w'])*float(parameters['l']), node))
        if candidates:
            result['COPY' if name == 'VCOPY' else name] = list(dict.fromkeys(n for _, n in sorted(candidates)))
    if 'CTRL' not in result:
        raise ValueError('Extracted candidate lacks a CTRL storage-capacitor terminal')
    return result


def assemble(layout, pfd, fast_rc=False):
    layout = Path(layout).resolve()
    pfd = Path(pfd).resolve()
    physical = json.loads((layout / 'summary.json').read_text())
    source_path = layout / 'candidate.spice'
    source = source_path.read_text()
    if not physical.get('passed') or digest(source_path) != physical['source_sha256']:
        raise ValueError('Candidate source or physical qualification changed')
    name = 'openlvds_dll_analog'
    circuit = physical['designs'][name]
    definitions = circuits(source)
    ports, devices = flatten(definitions, name)
    expected_scope = hashlib.sha256(schematic_text(name, ports, devices).encode()).hexdigest()
    if ports != ANALOG_PORTS or circuit['lvs_source_sha256'] != expected_scope:
        raise ValueError('Candidate analog schematic scope or interface changed')
    analog = json.loads((layout / 'extraction.json').read_text())
    if not (analog['ports'] == ports and analog['source_sha256'] == physical['source_sha256'] and
            analog['source_scope_sha256'] == expected_scope and
            digest(ROOT / circuit['gds']) == analog['gds_sha256']):
        raise ValueError('Candidate analog extraction is stale')
    audited(layout, analog)
    observations = observation_nodes(checked_netlist(analog))
    digital = json.loads((pfd / 'summary.json').read_text())
    if captured_inputs(pfd, digital) != 'lvds_pfd':
        raise ValueError('Expected the isolated pulse-area PFD')
    nl = ROOT / digital['run'] / 'final/nl/lvds_pfd.nl.v'
    if not pfd_candidate_paths_retained(nl.read_text(),digital.get('pfd_policy')) or not delay_cells_absent(nl.read_text()):
        raise ValueError('PFD no longer retains its declared native topology')
    detector = json.loads((pfd / 'extraction.json').read_text())
    if not (detector['source_sha256'] == digital['source_sha256'] and
            digest(ROOT / digital['run'] / 'final/gds/lvds_pfd.gds') == detector['gds_sha256']):
        raise ValueError('PFD extraction is stale')
    audited(pfd, detector)
    source_inputs = {name: analog['netlist_sha256'], 'lvds_pfd': detector['netlist_sha256']}
    if fast_rc:
        analog = approximate(layout, analog)
        detector = approximate(pfd, detector)
        if observation_nodes(checked_netlist(analog)) != observations:
            raise ValueError('Approximation changed storage-capacitor observation terminals')
    source = replace(source, name, checked_netlist(analog))
    # The bias source remains the same audited active macro, not a second diode.
    bias_library, bias_inputs, _ = library(extracted=True, designs={'lvds_bias'})
    bias_audit = json.loads((ROOT/'build/rc_audit/summary.json').read_text())['designs']['lvds_bias']
    if not (bias_audit.get('passed') and bias_audit['netlist_sha256'] == bias_inputs['lvds_bias'] and
            digest(ROOT/bias_audit['report']) == bias_audit['report_sha256']):
        raise ValueError('Bias extraction lacks a current independent RC audit')
    source = replace(source, 'lvds_bias', text_block(bias_library.decode(), 'lvds_bias'))
    expected = definitions['lvds_pfd'][0]
    if expected != PFD_PORTS:
        raise ValueError('Candidate PFD schematic terminals changed')
    mapping = {p: p for p in expected}
    mapping.update(VPWR='VDDD', VGND='VSS')
    if len(detector['ports']) != len(expected) or {mapping.get(p) for p in detector['ports']} != set(expected):
        raise ValueError('PFD extracted terminals differ from candidate schematic')
    body = checked_netlist(detector)
    body = re.sub(r'(?im)^(\.subckt\s+)lvds_pfd\b', r'\1lvds_pfd_physical', body)
    body = re.sub(r'(?im)^(\.ends\s+)lvds_pfd\b', r'\1lvds_pfd_physical', body)
    adapter = ('.subckt lvds_pfd ' + ' '.join(expected) + '\nXPHYS ' +
               ' '.join(mapping[p] for p in detector['ports']) + ' lvds_pfd_physical\n.ends lvds_pfd')
    source = replace(source, 'lvds_pfd', body + '\n' + adapter)
    result = closure(source, ['openlvds_dll'])
    if bias_reference_count('XL CLK RST EN P0 P90 P180 P270 FB BAD UP DN VR PB VA VD 0 openlvds_dll', result) != 1:
        raise ValueError('Assembled DLL must contain exactly one reference generator')
    metadata = dict(approximate_transient=fast_rc, qualified=False, layout=str(layout.relative_to(ROOT)),
                    pfd=str(pfd.relative_to(ROOT)),pfd_policy=digital['pfd_policy'],source_sha256=physical['source_sha256'],
                    full_inputs=dict(source_inputs, **bias_inputs), observation_nodes=observations,
                    inputs={name: analog['netlist_sha256'], 'lvds_pfd': detector['netlist_sha256'], **bias_inputs},
                    physical_reports={str(p.relative_to(ROOT)): digest(p) for p in
                        [layout/'summary.json', layout/'extraction.json', layout/'rc_audit.json',
                         pfd/'summary.json', pfd/'extraction.json', pfd/'rc_audit.json', nl]})
    return result, metadata
