# SPDX-License-Identifier: GPL-3.0-only
"""Generate and check the exact standard-cell PFD input-conditioning topology.

This is a connectivity policy, not a matched-routing or electrical certificate.
It deliberately leaves the original fast-reset policy and its evidence intact.
"""
from collections import Counter
import re

from pfd_fast_reset_policy import pfd_fast_reset_paths_retained, pins

VARIANTS = ('clkbuf_4', 'clkbuf_8', 'nor3_inv4', 'nor4_inv4')
PORTS = {'REF', 'FB', 'RESET_N', 'PD_ENABLE', 'UP', 'DN'}
POWER = {'VPWR', 'VGND', 'VPB', 'VNB'}


def chains(variant):
    if variant not in VARIANTS: raise ValueError('Unknown bounded PFD frontend')
    result = {}
    for side, external in [('ref', 'REF'), ('fb', 'FB')]:
        conditioned = side + '_conditioned'
        if variant.startswith('clkbuf'):
            result[side + '_condition'] = (variant, dict(A=external, X=conditioned))
        else:
            count = int(variant[3]); middle = side + '_mid'
            result[side + '_condition'] = (f'nor{count}_1', dict(**{p: external for p in 'ABCD'[:count]}, Y=middle))
            result[side + '_restore'] = ('inv_4', dict(A=middle, Y=conditioned))
    return result


def source(base, variant):
    if not pfd_fast_reset_paths_retained(base): raise ValueError('Require the original fast-reset PFD source')
    gates = chains(variant)
    for before, after in [('REF', 'ref_conditioned'), ('FB', 'fb_conditioned')]:
        base, count = re.subn(r'\.CLK\(\s*' + before + r'\s*\)', '.CLK(' + after + ')', base)
        if count != 1: raise ValueError('Require one direct clock input per PFD flip-flop')
    nodes = ['ref_conditioned', 'fb_conditioned'] + ([] if variant.startswith('clkbuf') else ['ref_mid', 'fb_mid'])
    lines = ['    (* keep="true" *) wire ' + ', '.join(nodes) + ';']
    for name, (kind, ports) in gates.items():
        lines += ['    (* keep="true", dont_touch="true" *)',
                  '    sky130_fd_sc_hd__' + kind + ' ' + name + '(' + ','.join('.' + p + '(' + n + ')' for p, n in ports.items()) + ');']
    result, count = re.subn(r'(?m)^endmodule\s*$', lambda m: '\n'.join(lines) + '\nendmodule', base)
    if count != 1 or not retained(result, variant): raise ValueError('Generated PFD violates its topology policy')
    return result


def retained(netlist, variant):
    """Check source and final flat gate netlists, including clock-net isolation."""
    expected = chains(variant)
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', netlist, flags=re.S)
    if re.search(r'\b(assign|always|initial|tran|alias)\b', text): return False
    headers = list(re.finditer(r'\bmodule\s+(\w+)\s*\((.*?)\);', text, re.S))
    if len(headers) != 1 or headers[0][1] != 'lvds_pfd': return False
    header = re.sub(r'(?m)^\s*`[^\n]*', '', headers[0][2])
    tokens = set(re.findall(r'\b\w+\b', header)) - {'wire', 'input', 'output', 'inout'}
    if not PORTS <= tokens or tokens - PORTS - {'VPWR', 'VGND'}: return False
    found = list(re.finditer(r'\b(\w+)\s+(\w+)\s*\((.*?)\);', text, re.S))
    instances = {}
    for match in found:
        kind, name, body = match.groups()
        if kind == 'module': continue
        if name in instances or not kind.startswith('sky130_fd_sc_hd__'): return False
        parsed = pins(body)
        # Reject positional connections and duplicate formal pins.
        if re.sub(r'\.\w+\s*\(\s*[^()\s]+\s*\)\s*,?\s*', '', body).strip(): return False
        if len(re.findall(r'\.\w+\s*\(', body)) != len(parsed): return False
        instances[name] = (kind.removeprefix('sky130_fd_sc_hd__'), parsed, match)
    core = {'ref_ff': 'dfrtp_4', 'fb_ff': 'dfrtp_4', 'up_drive': 'buf_8',
            'dn_drive': 'buf_8', 'reset_disable': 'nand2_1', 'clear': 'a22oi_4'}
    core_pins = {'dfrtp_4': {'CLK', 'D', 'RESET_B', 'Q'}, 'buf_8': {'A', 'X'},
                 'nand2_1': {'A', 'B', 'Y'}, 'a22oi_4': {'A1', 'A2', 'B1', 'B2', 'Y'}}
    for name, (kind, ports, _) in instances.items():
        if name in core:
            if kind != core[name] or set(ports) - POWER != core_pins[kind]: return False
        elif name in expected:
            wanted_kind, wanted_ports = expected[name]
            if kind != wanted_kind or {p: n for p, n in ports.items() if p not in POWER} != wanted_ports: return False
        elif kind != 'conb_1' and not re.fullmatch(r'(fill_\d+|tapvpwrvgnd_1|decap_\d+)', kind):
            return False
        elif kind == 'conb_1':
            if set(ports) - POWER - {'HI', 'LO'}: return False
        elif set(ports) - POWER: return False
        for pin, net in ports.items():
            if pin in POWER and net != ('VPWR' if pin in {'VPWR', 'VPB'} else 'VGND'): return False
    if not set(core) | set(expected) <= set(instances): return False
    # Accept flat declarations and the inspected named cell instances only.
    # In particular, declaration initializers and unnamed Verilog primitives
    # cannot bypass the clock connectivity checks below.
    remaining = text.replace(headers[0][0], '')
    for _, _, match in instances.values(): remaining = remaining.replace(match[0], '')
    remaining = re.sub(r'\(\*.*?\*\)', '', remaining, flags=re.S)
    remaining = re.sub(r'(?m)^\s*`[^\n]*', '', remaining)
    declarations = re.compile(r'\b(?:input|output|inout|wire)\b[^;]*;')
    if any('=' in m[0] for m in declarations.finditer(remaining)): return False
    remaining = declarations.sub('', remaining)
    if re.sub(r'\bendmodule\b', '', remaining).strip(): return False
    # External clocks, intermediate NOR outputs and delivered FF clocks may
    # touch exactly the specified pins. No bypass, extra load or cross-coupling.
    clock_nodes = {'REF', 'FB', 'ref_conditioned', 'fb_conditioned'}
    if not variant.startswith('clkbuf'): clock_nodes |= {'ref_mid', 'fb_mid'}
    wanted = Counter((name, pin, net) for name, (_, ports) in expected.items() for pin, net in ports.items())
    wanted.update([('ref_ff', 'CLK', 'ref_conditioned'), ('fb_ff', 'CLK', 'fb_conditioned')])
    actual = Counter((name, pin, net) for name, (_, ports, _) in instances.items()
                     for pin, net in ports.items() if net in clock_nodes)
    if actual != wanted: return False
    core_text = text
    for name in expected:
        core_text = core_text.replace(instances[name][2][0], '')
    core_text = re.sub(r'\.CLK\(\s*ref_conditioned\s*\)', '.CLK(REF)', core_text)
    core_text = re.sub(r'\.CLK\(\s*fb_conditioned\s*\)', '.CLK(FB)', core_text)
    return pfd_fast_reset_paths_retained(core_text)


def blackboxes(variant):
    """Only add cells absent from the frozen existing PFD blackbox file."""
    chains(variant)
    kinds = [variant] if variant.startswith('clkbuf') else [f'nor{variant[3]}_1']
    lines = ['// SPDX-License-Identifier: GPL-3.0-only', '`default_nettype none']
    for kind in kinds:
        inputs = 'A' if kind.startswith('clkbuf') else ','.join('ABCD'[:int(kind[3])])
        output = 'X' if kind.startswith('clkbuf') else 'Y'
        lines.append('(* blackbox *) module sky130_fd_sc_hd__' + kind + '(input wire ' + inputs + ',output wire ' + output + '); endmodule')
    return '\n'.join(lines + ['`default_nettype wire', ''])
