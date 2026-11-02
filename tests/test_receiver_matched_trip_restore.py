# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_matched_trip_restore as factory
import screen_receiver_matched_trip as screen
from layout import circuits,flatten


class MatchedTripRestoration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()

    def test_control_remains_byte_identical(self):
        self.assertEqual(factory.source_variant(self.source,'control'),factory.previous.source_variant(self.source,'control'))

    def test_reference_is_two_exact_first_inverter_units(self):
        for variant in factory.VARIANTS[1:]:
            source=factory.source_variant(self.source,variant);defs=circuits(source)
            rows={r[0]:r for r in defs[factory.TOP][1]}
            self.assertEqual(rows['XTRACK'][2],factory.HELPER)
            first=defs[rows['XIB0'][2]][1];reference=defs[factory.HELPER][1]
            signature=lambda rows:Counter((tuple(r[1]),r[2],tuple(sorted(r[3].items()))) for r in rows)
            self.assertEqual(signature(reference),signature(first+first))
            self.assertEqual(len(reference),4)

    def test_physical_finger_devices_and_connectivity_are_unchanged(self):
        for variant,old in [('matched_t8_r7','track_t8_r7'),('matched_t16_r7','track_t16_r7')]:
            a=flatten(circuits(factory.source_variant(self.source,variant)),factory.TOP)
            b=flatten(circuits(factory.previous.source_variant(self.source,old)),factory.TOP)
            self.assertEqual(a[0],b[0]); self.assertEqual(len(a[1]),len(b[1]))
            signature=lambda ds:Counter((tuple(d['nodes']),d['model'],tuple(sorted(d['params'].items()))) for d in ds)
            self.assertEqual(signature(a[1]),signature(b[1]))

    def test_source_observer_includes_all_four_reference_devices(self):
        for variant in factory.VARIANTS:
            source=factory.source_variant(self.source,variant);observed=screen.observed_devices(screen.instrument(source))
            self.assertEqual(len(observed),14 if variant=='control' else 21)
            if variant!='control':
                self.assertEqual({n for n in observed if n.startswith('XTRACK/')},{'XTRACK/XP0','XTRACK/XP1','XTRACK/XN0','XTRACK/XN1'})

    def test_repeated_or_unknown_transformation_is_rejected(self):
        with self.assertRaises(ValueError):factory.source_variant(self.source,'track_t8_r7')
        modified=factory.source_variant(self.source,'matched_t8_r7')
        with self.assertRaises(ValueError):factory.transform(modified,'matched_t16_r7')
