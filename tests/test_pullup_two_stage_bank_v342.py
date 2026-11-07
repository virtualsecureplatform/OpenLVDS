# SPDX-License-Identifier: GPL-3.0-only
"""Keep full-bank P40 input-loading and range qualification at original limits."""
import copy
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import probe_pullup_two_stage_bank_v342 as probe

PARENT = ROOT/'build/diagnostics/two_stage_fine_bank_v322/4092d10edbdce08c'
MATERIALS = ROOT/'build/diagnostics/recovery_fine_driver_rc_v340/be4316b0effe7c22'


class FullBankPullupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity = json.loads((PARENT/'manifest.json').read_text())['identity']
        cls.bank = (PARENT/'bank.spice').read_text()
        row = json.loads((MATERIALS/'summary.json').read_text())['rows'][0]
        cls.cell = probe.source.source.cell_definition((ROOT/row['extraction']['netlist']).read_text(), probe.MODEL)
        cls.changed, cls.observations = probe.transform(cls.bank, cls.identity['observations'], cls.cell)

    def test_actual_full_bank_and_all_non_loaded_native_maps_and_calls_are_retained(self):
        self.assertEqual(len(self.observations['devices']), 1385)
        self.assertEqual(len(self.observations['controls']), 86)
        self.assertEqual(len(self.observations['programming_gates']), 173)
        prefix = 'XD:Xfine_isolate:'
        old = {d['name']: d for d in self.identity['observations']['devices'] if not d['name'].startswith(prefix)}
        new = {d['name']: d for d in self.observations['devices'] if not d['name'].startswith(prefix)}
        self.assertEqual(len(old), 1329)
        self.assertEqual(old, new)
        definitions = probe.source.source.native.definitions
        before, after = definitions(self.bank), definitions(self.changed)
        self.assertEqual([w for w in before[probe.source.TOP][1] if w[0] != 'Xfine_isolate'],
                         [w for w in after[probe.TOP][1] if w[0] != 'Xfine_isolate'])
        for name in before:
            if name != probe.source.TOP:
                self.assertEqual(before[name], after[name])

    def test_complete_original_clock_load_programming_and_probe_fixture_is_retained(self):
        identity = dict(self.identity, observations=self.observations)
        self.assertEqual([(s['coarse'], s['fine'], s['duty']) for s in probe.specifications()],
                         [(0, 0, .5), (0, 31, .6), (0, 31, .4), (1, 0, .5)])
        for spec, original_spec in zip(probe.specifications(), probe.source.specifications()):
            text = probe.fixture(PARENT, identity, spec)
            old = probe.source.fixture(PARENT, self.identity, original_spec)
            for prefix in ('BIN ', 'VDD ', '.tran ', 'CLOAD ', 'VS', 'VE'):
                self.assertEqual([l for l in text.splitlines() if l.startswith(prefix)],
                                 [l for l in old.splitlines() if l.startswith(prefix)])
            probes = set(re.findall(r'V\(([^)]+)\)', next(l for l in text.splitlines() if l.startswith('.print '))))
            self.assertTrue({n for d in self.observations['devices'] for n in d['terminals'] if n != '0'} <= probes)
            self.assertNotIn('Rboundary', text)
            self.assertNotIn('VREPLAY', text)

    def test_partial_or_wrong_driver_component_is_rejected(self):
        for text in (self.cell.replace(' A Y VGND VPWR', ' Y A VGND VPWR', 1),
                     self.cell.replace(probe.MODEL, 'wrong_model')):
            with self.assertRaisesRegex(ValueError, 'exact qualified P40'):
                probe.transform(self.bank, self.identity['observations'], text)
        old = 'Xfine_isolate selected fine_node VGND VPWR '+probe.source.source.MODEL
        with self.assertRaisesRegex(ValueError, 'Original full-bank'):
            probe.transform(self.bank.replace(old, old.replace('fine_node', 'OUT'), 1),
                            self.identity['observations'], self.cell)

    def test_original_failed_overlap_and_incomplete_coverage_cannot_be_admitted(self):
        rows = json.loads((PARENT/'summary.json').read_text())['rows']
        changed = [dict(row, spec=probe.specifications()[k]) for k, row in enumerate(rows)]
        self.assertEqual(probe.compare(changed), probe.source.compare(rows))
        self.assertFalse(probe.compare(changed)['component_hypothesis_passed'])
        self.assertTrue(all(v < 0 for v in probe.compare(changed)['conservative_coarse_overlap_ps'].values()))
        self.assertIsNone(probe.compare(changed[:3]))
        failed = copy.deepcopy(changed)
        failed[1]['error'] = 'missing native trace'
        self.assertIsNone(probe.compare(failed))


if __name__ == '__main__':
    unittest.main()
