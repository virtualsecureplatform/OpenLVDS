# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_pmos_clock as clock
from layout import circuits

ROOT = Path(__file__).resolve().parents[1]


class PMOSSourceClock(unittest.TestCase):
    def test_baseline_reference_and_pmos_intervention_remain_distinct(self):
        source = (ROOT/'analog/openlvds.spice').read_text()
        def pair(modified):
            return {r[0]: r for r in circuits(clock.source_variant(source, modified))['openlvds_receiver_core'][1]}['XC0']
        self.assertEqual(pair(False)[2], 'sky130_fd_pr__nfet_01v8')
        self.assertEqual(pair(True)[2], 'sky130_fd_pr__pfet_g5v0d10v5')

    def test_incomplete_dc_matrix_cannot_start_a_scientific_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); screen = root/'build/diagnostics/receiver_architecture_matrix/test'; screen.mkdir(parents=True)
            (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(variant=clock.VARIANT, children=[dict(root='missing')]*15))))
            with patch.object(clock, 'ROOT', root), patch.object(clock.matrix, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Complete all fifteen'):
                    clock.static_gate(screen)
                run.assert_not_called()

    def test_factory_bindings_restore_when_clock_analysis_raises(self):
        previous = clock.clock.factory, clock.clock.static_gate, clock.engine.source_variant
        with self.assertRaises(RuntimeError):
            with clock.profile():
                self.assertIs(clock.clock.factory.source_variant, clock.source_variant)
                raise RuntimeError('test failure')
        self.assertEqual(previous, (clock.clock.factory, clock.clock.static_gate, clock.engine.source_variant))


if __name__ == '__main__':
    unittest.main()
