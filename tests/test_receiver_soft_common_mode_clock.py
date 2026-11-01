# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_soft_common_mode_clock as clock


class SoftCommonModeClock(unittest.TestCase):
    def test_exact_softer_candidates_and_retained_reference(self):
        source = (clock.ROOT/'analog/openlvds.spice').read_text()
        for variant in clock.VARIANTS:
            self.assertEqual(clock.source_variant(source, True, variant),
                clock.dc.transform(clock.original.source_variant(source, True), variant))
            self.assertEqual(clock.source_variant(source, False, variant), clock.original.source_variant(source, False))
        for old in ['reference_return', 'rail_pullup']:
            with self.assertRaises(ValueError):
                clock.source_variant(source, True, old)

    def test_failed_old_matrix_cannot_admit_soft_candidate(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(clock, 'ROOT', Path(tmp)):
            with self.assertRaisesRegex(ValueError, 'DC matrix'):
                clock.static_gate(Path(tmp)/'build/diagnostics/receiver_common_mode_matrix/old', 'rail_pullup_2r')

    def test_missing_child_report_cannot_trigger_source_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); screen = root/'build/diagnostics/receiver_soft_common_mode_matrix/incomplete'
            screen.mkdir(parents=True)
            req = dict(process_corners=['tt','ff','ss','fs','sf'], temperatures_c=[0,25,40])
            (root/'requirements.json').write_text(json.dumps(req))
            children = [dict(process=p, temperature=t, case=f'schematic_receiver_{p}_{t}', root='missing')
                for p in req['process_corners'] for t in req['temperatures_c']]
            (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(children=children))))
            (screen/'summary.json').write_text('{}')
            with patch.object(clock, 'ROOT', root), patch.object(clock.matrix, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Complete all fifteen'):
                    clock.static_gate(screen, 'rail_pullup_2r')
                run.assert_not_called()

    def test_profile_restores_after_failure(self):
        previous = clock.clock.factory, clock.clock.static_gate
        with self.assertRaises(RuntimeError):
            with clock.profile('rail_pullup_3r'):
                source = (clock.ROOT/'analog/openlvds.spice').read_text()
                self.assertEqual(clock.clock.factory.source_variant(source, True), clock.source_variant(source, True, 'rail_pullup_3r'))
                raise RuntimeError('injected')
        self.assertEqual((clock.clock.factory, clock.clock.static_gate), previous)


if __name__ == '__main__':
    unittest.main()
