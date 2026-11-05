# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import layout
import moscap_fine_unit_v77 as unit
import moscap_junction_reconstruction_v86 as repair


class MeasuredGateCapJunctionTests(unittest.TestCase):
    def fixture(self):
        top = unit.name('w042'); reference = unit.schematic('w042')
        ports, devices = layout.flatten(layout.circuits(reference), top)
        rows = []; keys = set()
        for d in devices:
            if 'fet_' not in d['model']:
                continue
            key = repair.geometry_key(d)
            if key not in keys:
                keys.add(key)
                p = dict(ad='.1218', **{'as': '.1218'}, pd='1.42', ps='1.42')
                if float(d['params']['w']) == .84:
                    p = dict(ad='.2436', **{'as': '.22'}, pd='2.26', ps='2.1')
                # Deliberately report the isolated transistor with D/S exchanged.
                rows.append(dict(primitive=dict(model=d['model'], width_um=d['params']['w'],
                    length_um=d['params']['l'], cell='cell'+str(len(keys))),
                    geometry=dict(passed=True, drc_count='0'), actual=dict(model=d['model'],
                    nodes=['S', 'G', 'D', 'B'], params=dict(d['params'], **p))))
        library = repair.junction_library(rows)
        for d in devices:
            if 'fet_' not in d['model']:
                continue
            d['params'].update(library[repair.geometry_key(d)]['values'])
            if d['nodes'][0] == d['nodes'][2] == d['nodes'][3]:
                d['params'].update({'as': '0', 'ps': '0'})
            elif 'pfet_' in d['model']:
                d['nodes'][0], d['nodes'][2] = d['nodes'][2], d['nodes'][0]
                p = d['params']; p['ad'], p['as'] = p['as'], p['ad']; p['pd'], p['ps'] = p['ps'], p['pd']
        raw = layout.schematic_text(top, ports, devices).replace('.ends '+top,
            'Rwire NODE unused_wire 2.5\nCwire ENB VSS .5f $ retained comment\n.ends '+top)
        return top, reference, raw, rows

    def test_restores_two_tied_junctions_with_measured_ds_orientation_and_exact_passives(self):
        top, reference, raw, rows = self.fixture()
        corrected, full, proof = repair.reconstruct(raw, top, reference, rows)
        self.assertEqual(len(proof['corrections']), 2)
        self.assertTrue(proof['passive_lines_preserved'])
        self.assertTrue(proof['parameters']['all_reference_supplied_junctions_preserved'])
        self.assertIn('Rwire NODE unused_wire 2.5\nCwire ENB VSS .5f $ retained comment', corrected)
        self.assertIn('.subckt '+top+'_flat NODE EN ENB VDD VSS', full)

    def test_positive_mismatch_and_missing_measurement_are_rejected(self):
        top, reference, raw, rows = self.fixture()
        with self.assertRaisesRegex(ValueError, 'nonzero'):
            repair.reconstruct(raw.replace('as=0 ', 'as=.001 ', 1), top, reference, rows)
        with self.assertRaisesRegex(ValueError, 'Missing isolated'):
            repair.reconstruct(raw, top, reference, rows[:-1])

    def test_capacitor_gate_or_body_wiring_fault_is_rejected(self):
        top, reference, raw, rows = self.fixture()
        bad = raw.replace('VSS '+top+'__CAP VSS VSS', 'VSS ENB VSS VSS', 1)
        self.assertNotEqual(bad, raw)
        with self.assertRaisesRegex(ValueError, 'topology'):
            repair.reconstruct(bad, top, reference, rows)

    def test_asymmetric_tied_junction_and_duplicate_measurement_are_rejected(self):
        top, reference, raw, rows = self.fixture()
        bad = deepcopy(rows); bad[-1]['actual']['params']['as'] = '.2'
        with self.assertRaisesRegex(ValueError, 'asymmetric'):
            repair.reconstruct(raw, top, reference, bad)
        with self.assertRaisesRegex(ValueError, 'Invalid isolated'):
            repair.reconstruct(raw, top, reference, rows+[rows[0]])


if __name__ == '__main__':
    unittest.main()
