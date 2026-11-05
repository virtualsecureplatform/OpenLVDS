# SPDX-License-Identifier: GPL-3.0-only
"""Diagnostic ideal wiring for verified flat clock-buffer/fine component RC.

Remove only explicit extracted R/C elements. Preserve every native primitive,
parameter, body terminal and native MIM. This deliberately removes physical
parasitics and can never be consumed as a qualified physical timing model.
"""
from collections import Counter
import native_clock_components_v2 as native
from reduce_rc import number

VERSION = 'native-parameter-preserving-component-parasitic-isolation-v4.1'


def isolate(text, model):
    definitions = native.definitions(text)
    if set(definitions) != {model}:
        raise ValueError('Require one verified flat native component')
    ports, body = definitions[model]
    if len(ports) != len(set(ports)):
        raise ValueError('Duplicate native component ports')
    parents = {}
    def root(n):
        parents.setdefault(n, n)
        if parents[n] != n:
            parents[n] = root(parents[n])
        return parents[n]
    def join(a, b):
        a, b = root(a), root(b)
        if a != b:
            parents[b] = a
    resistors = capacitors = 0
    primitives = []
    for words in body:
        kind = words[0][0].upper()
        if kind in ('R', 'C'):
            values = words[:next((i for i, token in enumerate(words) if token.startswith('$')), len(words))]
            if len(values) != 4 or not (number(values[3]) > 0 if kind == 'R' else number(values[3]) >= 0):
                raise ValueError('Require positive routing R and nonnegative parasitic C')
            if kind == 'R':
                join(words[1], words[2]); resistors += 1
            else:
                capacitors += 1
        elif kind == 'X':
            end = next((i for i, token in enumerate(words) if '=' in token), len(words))
            leaf = words[end-1]
            if (not leaf.startswith('sky130_fd_pr__') or
                    not ('nfet_' in leaf or 'pfet_' in leaf or leaf == 'sky130_fd_pr__cap_mim_m3_1')):
                raise ValueError('Non-native or intentional resistor component')
            count = 2 if leaf == 'sky130_fd_pr__cap_mim_m3_1' else 4
            if len(words[1:end-1]) != count:
                raise ValueError('Native primitive terminal count changed')
            primitives.append((words, end))
        else:
            raise ValueError('Unexpected active component or source')
    if not resistors or not capacitors or not primitives:
        raise ValueError('Require a nonempty extracted native RC component')
    nodes = set(ports) | {'0'}
    for words, end in primitives:
        nodes.update(words[1:end-1])
    groups = {}
    for node in sorted(nodes | set(parents)):
        groups.setdefault(root(node), []).append(node)
    aliases = {}
    for members in groups.values():
        public = set(members) & (set(ports) | {'0'})
        if len(public) > 1:
            raise ValueError('Wire collapse would merge distinct public terminals')
        representative = next(iter(public)) if public else min(members)
        aliases.update({n: representative for n in members})
    rows = ['.subckt '+model+' '+' '.join(ports)]
    before = Counter(); after = Counter()
    for words, end in primitives:
        rewritten = [words[0], *[aliases[n] for n in words[1:end-1]], *words[end-1:]]
        # Name, model and the complete parameter list are byte-token identical.
        before[tuple([words[0], *words[end-1:]])] += 1
        after[tuple([rewritten[0], *rewritten[end-1:]])] += 1
        rows.append(' '.join(rewritten))
    if before != after:
        raise ValueError('Native primitive/geometry parameters changed')
    source = '\n'.join(rows+['.ends '+model, ''])
    report = dict(model=model, removed_explicit_resistors=resistors,
                  removed_explicit_parasitic_capacitors=capacitors,
                  retained_native_primitives=len(primitives), native_parameters_preserved=True,
                  public_ports=ports, wire_aliases=aliases, qualified_phy=False,
                  electrical_qualification_passed=False,
                  scope='Deliberate extracted-wire/parasitic removal for diagnosis only; native MOS/MIM parameters retained, no physical equivalence or timing admission')
    return source, report
