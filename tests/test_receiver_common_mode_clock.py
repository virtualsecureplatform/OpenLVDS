# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_common_mode_clock as cm


class CommonModeClock(unittest.TestCase):
    def test_exact_admitted_candidate_and_retained_reference(self):
        source = (cm.ROOT/'analog/openlvds.spice').read_text()
        for variant in cm.VARIANTS:
            self.assertEqual(cm.source_variant(source, True, variant),
                cm.dc.transform(cm.original.source_variant(source, True), variant))
            self.assertEqual(cm.source_variant(source, False, variant), cm.original.source_variant(source, False))
        with self.assertRaises(ValueError):
            cm.source_variant(source, True, 'control')

    def test_profile_restores_shared_bindings_after_failure(self):
        old = cm.clock.factory, cm.clock.static_gate
        with self.assertRaisesRegex(ValueError, 'injected'):
            with cm.profile('rail_pullup'):
                self.assertIs(cm.clock.factory.experiment, cm.engine)
                source = (cm.ROOT/'analog/openlvds.spice').read_text()
                self.assertEqual(cm.clock.factory.source_variant(source, True), cm.source_variant(source, True, 'rail_pullup'))
                raise ValueError('injected')
        self.assertEqual((cm.clock.factory, cm.clock.static_gate), old)

    def test_aggregate_report_cannot_launch_missing_static_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); screen = root/'build/diagnostics/receiver_common_mode_matrix/incomplete'
            screen.mkdir(parents=True)
            req = dict(process_corners=['tt', 'ff', 'ss', 'fs', 'sf'], temperatures_c=[0, 25, 40])
            (root/'requirements.json').write_text(json.dumps(req))
            children = []
            for p in req['process_corners']:
                for t in req['temperatures_c']:
                    child = root/f'children/{p}_{t}'; child.mkdir(parents=True)
                    (child/'summary.json').write_text('{}')
                    children.append(dict(root=str(child.relative_to(root)), process=p, temperature=t,
                        case=f'schematic_receiver_{p}_{t}'))
            (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(children=children))))
            (screen/'summary.json').write_text('{}')
            with patch.object(cm, 'ROOT', root), patch.object(cm.matrix, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Complete all fifteen'):
                    cm.static_gate(screen, 'reference_return')
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
