# SPDX-License-Identifier: GPL-3.0-only
"""Keep the P40 intervention confined to one qualified native loaded driver."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import probe_loaded_pullup_recovery_v341 as probe

PARENT = ROOT/'build/diagnostics/loaded_fine_recovery_v333/53cd1cb8b555e03e'
MATERIALS = ROOT/'build/diagnostics/recovery_fine_driver_rc_v340/be4316b0effe7c22'


class PullupRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity = json.loads((PARENT/'manifest.json').read_text())['identity']
        cls.previous = cls.identity['observations']['baseline']
        cls.bank = (PARENT/'baseline/bank.spice').read_text()
        row = json.loads((MATERIALS/'summary.json').read_text())['rows'][0]
        cls.cell = probe.source.source.source.cell_definition(
            (ROOT/row['extraction']['netlist']).read_text(), probe.MODEL)
        cls.changed, cls.observations = probe.transform(cls.bank, cls.previous, cls.cell)

    def test_only_loaded_native_driver_changes_and_every_other_terminal_is_retained(self):
        self.assertEqual(len(self.observations['devices']), 433)
        prefix = 'XD:Xfine_isolate:'
        old = {d['name']: d for d in self.previous['devices'] if not d['name'].startswith(prefix)}
        new = {d['name']: d for d in self.observations['devices'] if not d['name'].startswith(prefix)}
        self.assertEqual(len(old), 377)
        self.assertEqual(old, new)
        self.assertEqual(self.observations['controls'], self.previous['controls'])
        self.assertEqual(self.observations['programming_gates'], self.previous['programming_gates'])
        definitions = probe.source.source.source.native.definitions
        before, after = definitions(self.bank), definitions(self.changed)
        for name in before:
            if name != probe.source.TOP:
                self.assertEqual(before[name], after[name])
        body = after[probe.TOP][1]
        self.assertEqual(sum(w[0].startswith('Xfine_unit') for w in body), 31)
        self.assertEqual([w for w in body if w[0] == 'Xfine_regenerate1'],
            [['Xfine_regenerate1', 'fine_node', 'OUT', 'VGND', 'VPWR', probe.source.MODELS['baseline']]])
        self.assertEqual([w for w in body if w[0] == 'Rboundary'], [['Rboundary', 'selected', 'REPLAY', '1m']])

    def test_source_waveform_all_startup_events_stop_load_and_native_probes_stay(self):
        identity = dict(self.identity, observations={probe.VARIANT: self.observations})
        old = self.identity['original_fixture'].splitlines()
        lines = probe.fixture(PARENT, identity).splitlines()
        for prefix in ('BIN ', '.tran ', 'CLOAD ', 'VDD '):
            self.assertEqual(next(l for l in lines if l.startswith(prefix)),
                             next(l for l in old if l.startswith(prefix)))
        probes = set(re.findall(r'V\(([^)]+)\)', next(l for l in lines if l.startswith('.print '))))
        self.assertTrue({n for d in self.observations['devices'] for n in d['terminals'] if n != '0'} <= probes)
        self.assertIn('REPLAY', probes)
        self.assertIn('XD:fine_node', probes)

    def test_missing_or_rewired_retained_cell_and_wrong_loaded_driver_are_rejected(self):
        for old, new in [('Xfine_unit30 fine_node', 'Xfine_unit30 OUT'),
                         ('Xfine_regenerate1 fine_node', 'Xfine_regenerate1 selected'),
                         ('Rboundary selected REPLAY 1m', 'Rboundary selected REPLAY 1')]:
            self.assertIn(old, self.bank)
            with self.assertRaisesRegex(ValueError, 'Non-loaded native terminals'):
                probe.transform(self.bank.replace(old, new, 1), self.previous, self.cell)
        old = 'Xfine_isolate selected fine_node VGND VPWR '+probe.source.MODELS['baseline']
        with self.assertRaisesRegex(ValueError, 'Original replayed'):
            probe.transform(self.bank.replace(old, old.replace('fine_node', 'OUT'), 1), self.previous, self.cell)

    def test_wrong_component_port_order_or_namespace_is_rejected(self):
        for cell in (self.cell.replace(' A Y VGND VPWR', ' Y A VGND VPWR', 1),
                     self.cell.replace(probe.MODEL, 'wrong_p40_model')):
            with self.assertRaisesRegex(ValueError, 'exact qualified native P40'):
                probe.transform(self.bank, self.previous, cell)


if __name__ == '__main__':
    unittest.main()
