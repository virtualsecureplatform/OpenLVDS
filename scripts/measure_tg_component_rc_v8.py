# SPDX-License-Identifier: GPL-3.0-only
"""Read all active-terminal checks even when a passive public node is unsaved.

Do not infer its voltage. Every MOS terminal and distributed control gate
remains mandatory; public-tail range is a separate optional observation.
"""
import re
import numpy as np
import probe_dcdl_tg_component_rc_v7 as producer
from native_binary_raw_v2 import validate


def add_public_probes(text):
    """For future decks only; never mutate a bound or running fixture."""
    matches = list(re.finditer(r'(?im)^\.print\s+tran\s+(.+)$', text))
    if len(matches) != 1:
        raise ValueError('Require one native voltage print statement')
    match = matches[0]
    names = {n.replace(':', '.').lower() for n in re.findall(r'V\(([^)]+)\)', match[1], re.I)}
    if 'xd.unused_tail' in names:
        return text
    return text[:match.end()]+' V(XD:unused_tail)'+text[match.end():]


def measure(folder, spec, devices, gates):
    # v5 contains the same complete MOS/pulse/public-control checks, without
    # v6's extra public-tail probe requirement. No active terminal is omitted.
    result = producer.previous.previous.measure(folder, spec, devices)
    tail = [d for d in result['terminal_stress'] if d['device'].startswith('XD:Xtail_load:')]
    if not tail:
        raise ValueError('Missing balancing-buffer native device coverage')
    def column(n):
        return 'v('+n.replace(':', '.').lower()+')'
    names, w = validate(folder/'bench.raw', {column(g['gate_node']) for g in gates}, 20e-9)
    idx = {n: i for i, n in enumerate(names)}; stable = w[:, idx['time']] >= 1.5e-9
    controls = []
    for gate in gates:
        enabled = int(gate['bit'] < spec['fine'])
        target = 1.8*(enabled if gate['kind'] == 'fine' else 1-enabled)
        deviation = float(np.max(np.abs(w[stable, idx[column(gate['gate_node'])]]-target)))
        controls.append(dict(gate, maximum_deviation_v=deviation, passed=bool(deviation <= .18)))
    public = result['control_settling_passed']; internal = all(c['passed'] for c in controls)
    vector = 'v(xd.unused_tail)'; available = vector in idx
    result.update(public_control_settling_passed=public, distributed_fine_controls=controls,
                  distributed_control_settling_passed=internal, control_settling_passed=bool(public and internal),
                  public_tail_range_available=available,
                  tail_output_minimum_v=float(np.min(w[:, idx[vector]])) if available else None,
                  tail_output_maximum_v=float(np.max(w[:, idx[vector]])) if available else None,
                  balancing_buffer_terminal_screen_passed=all(d['passed'] for d in tail),
                  balancing_buffer_max_terminal_difference_v=max(d['maximum_terminal_difference_v'] for d in tail),
                  tail_termination_um=[2, 2], component_parasitics_retained=True,
                  physical_parasitics_retained=False, whole_bank_rc_retained=False,
                  electrical_qualification_passed=False, qualified_phy=False, scope=producer.SCOPE)
    return result
