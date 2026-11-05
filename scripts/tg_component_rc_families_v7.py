# SPDX-License-Identifier: GPL-3.0-only
"""Restore exact verified component RC without changing native parameters.

The TGs/common wiring remain unextracted. This is not whole-bank RC proof.
"""
import dcdl_tg_terminated_v6 as circuit
import native_clock_components_v2 as native
from build_compound_drivers_v3 import cell_definition
from spice_library import replace
from uniform_tree_parasitic_isolation_v4 import isolate

REQUIRED = {circuit.previous.BUFFER, circuit.previous.INVERTER, circuit.previous.FINE}


def restore(cells, components):
    if set(components) != REQUIRED:
        raise ValueError('Require all three original verified component RC models')
    before = native.definitions(cells); restored = cells; reports = []
    for model in sorted(REQUIRED):
        text = components[model]
        ideal, report = isolate(text, model)
        if cell_definition(cells, model).strip() != ideal.strip():
            raise ValueError('RC does not reproduce the exact parameter-preserving source component: '+model)
        restored = replace(restored, model, text.rstrip())
        if native.definitions(restored)[model] != native.definitions(text)[model]:
            raise ValueError('Restored component RC elements or interface changed')
        reports.append(dict(model=model, restored_resistors=report['removed_explicit_resistors'],
                            restored_parasitic_capacitors=report['removed_explicit_parasitic_capacitors'],
                            retained_native_primitives=report['retained_native_primitives'],
                            native_parameters_preserved=True))
    after = native.definitions(restored)
    if set(after) != set(before) or any(after[n] != before[n] for n in before if n not in REQUIRED):
        raise ValueError('RC restoration changed unrelated TG/control definitions')
    return restored, reports


def fine_gate_observations(component, bank, expected_units=31):
    """Map actual R-separated switch gates to their external control targets."""
    model = circuit.previous.FINE
    _, report = isolate(component, model)
    aliases = report['wire_aliases']; ports, body = native.definitions(component)[model]
    roots = native.definitions(bank)
    if len(roots) != 1:
        raise ValueError('Require one native bank root')
    root_ports, instances = next(iter(roots.values()))
    gates = []
    for words in body:
        if not words[0].startswith('X'):
            continue
        end = next((i for i, value in enumerate(words) if '=' in value), len(words))
        if words[end-1] == 'sky130_fd_pr__cap_mim_m3_1':
            continue
        if len(words[1:end-1]) != 4 or aliases.get(words[2]) not in ('EN', 'ENB'):
            raise ValueError('Unrecognized native fine control gate')
        gates.append((words[0], words[2], aliases[words[2]]))
    if len(gates) != 3:
        raise ValueError('Fine unit must retain all three actual switch/clamp gates')
    def root_node(n):
        return '0' if n in ('VGND', '0') else 'VDD' if n == 'VPWR' else n if n in root_ports else 'XD:'+n
    result = []; indices = []
    for words in instances:
        if words[-1] != model:
            continue
        tag = words[0]
        if not tag.startswith('Xfine_unit') or not tag[len('Xfine_unit'):].isdigit() or len(words[1:-1]) != len(ports):
            raise ValueError('Changed fine-unit instance/interface')
        bit = int(tag[len('Xfine_unit'):]); indices.append(bit)
        mapping = dict(zip(ports, words[1:-1]))
        for primitive, gate, control in gates:
            actual = root_node(mapping[gate]) if gate in mapping else 'XD:'+tag+':'+gate
            result.append(dict(device='XD:'+tag+':'+primitive, gate_node=actual,
                               control_node=root_node(mapping[control]), bit=bit,
                               kind='fine' if control == 'EN' else 'fine_b'))
    if sorted(indices) != list(range(expected_units)):
        raise ValueError('Missing or repeated fine-unit control observations')
    return result
