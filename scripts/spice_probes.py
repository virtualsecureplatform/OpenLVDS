# SPDX-License-Identifier: GPL-3.0-only
"""Reject missing hierarchical voltage probes before a long SPICE transient."""
import re


def scope(text):
    nodes = set()
    children = {}
    header = False
    for line in text.splitlines():
        words = line.lower().split()
        if not words or words[0].startswith('*'):
            continue
        tag = words[0]
        if tag == '.subckt':
            nodes.update(words[2:])
            header = True
        elif tag == '+' and header:
            nodes.update(words[1:])
        else:
            header = False
        if tag.startswith('x'):
            end = next((i for i, value in enumerate(words) if '=' in value), len(words))
            nodes.update(words[1:end-1])
            children[tag] = words[end-1]
        elif tag[0] in 'rcvil':
            nodes.update(words[1:3])
    return nodes, children


class ProbeNetwork:
    def __init__(self, library):
        self.definitions = {match[1].lower(): scope(match[0]) for match in re.finditer(
            r'(?ims)^\.subckt\s+(\S+)\s.*?^\.ends[^\n]*', library)}

    def validate(self, deck, probes):
        top = scope(deck)
        for probe in probes:
            current = top
            parts = probe.lower().split(':')
            for instance in parts[:-1]:
                if instance not in current[1] or current[1][instance] not in self.definitions:
                    raise ValueError('Missing probe hierarchy: ' + probe)
                current = self.definitions[current[1][instance]]
            if parts[-1] not in current[0]:
                raise ValueError('Missing voltage probe node: ' + probe)
