# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_architecture as physical


class ArchitecturePhysicalAdmission(unittest.TestCase):
    def fixture(self, root):
        matrix = root/'build/diagnostics/receiver_architecture_matrix/test'; matrix.mkdir(parents=True)
        children = []
        for process, temperature in [('tt', 25), ('sf', 40), ('fs', 40)]:
            folder = root/(process+str(temperature)); folder.mkdir()
            (folder/'manifest.json').write_text(json.dumps(dict(identity=dict(architecture_variant='pmos_p8_t4'))))
            (folder/'summary.json').write_text('{}')
            children.append(dict(process=process, temperature=temperature, root=str(folder.relative_to(root)), manifest_sha256=physical.sha(folder/'manifest.json')))
        (matrix/'manifest.json').write_text(json.dumps(dict(identity=dict(children=children, variant='pmos_p8_t4', inputs={}, code={}))))
        rate = root/'rate'; rate.mkdir(); (rate/'summary.json').write_text('{}')
        return matrix, children, rate

    def test_incomplete_dc_pilot_cannot_trigger_scientific_runs_or_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); matrix, children, rate = self.fixture(root)
            (root/children[-1]['root']/'summary.json').unlink()
            with patch.object(physical, 'ROOT', root), patch.object(physical.observed, 'run') as dc, patch.object(physical.rate, 'run') as dynamic:
                with self.assertRaisesRegex(ValueError, 'Complete all three'):
                    physical.source_gate(matrix, rate)
                dc.assert_not_called(); dynamic.assert_not_called()

    def test_failed_or_different_rate_variant_cannot_admit_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); matrix, children, rate = self.fixture(root)
            report = dict(architecture=dict(metrics=dict(passed=True), observations=dict(observed_thin_guard_passed=True)))
            # Pilot fixture hashes are captured only after successful admission.
            for child in children:
                for name in ['source.spice', 'bench.cir', 'bench.cir.prn']:
                    (root/child['root']/name).write_text('captured')
            for variant, passed in [('pmos_p8_t4', False), ('lvt', True)]:
                with patch.object(physical, 'ROOT', root), patch.object(physical.observed, 'run', return_value=report), patch.object(physical.rate, 'run', return_value=dict(variant=variant, metrics=dict(passed=passed))):
                    with self.assertRaisesRegex(ValueError, 'failed or differs'):
                        physical.source_gate(matrix, rate)


if __name__ == '__main__':
    unittest.main()
