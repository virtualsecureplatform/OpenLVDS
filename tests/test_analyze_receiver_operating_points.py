# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyze_receiver_operating_points as analysis


class RetainedOperatingPoints(unittest.TestCase):
    def fixture(self):
        values = {'v(' + n.replace(':', '.').lower() + ')': 0. for n in analysis.probe.NODES}
        values['v(n)'] = .1
        values.update({'i(vio)': -.001, 'i(vdig)': -.0001, 'i(vref)': -.0002})
        for field, alias, value in [('id', 'i(tail_id)', .0001), ('gm', 'tail_gm', .001),
                                   ('gds', 'tail_gds', .0001), ('vdsat', 'v(tail_vdsat)', .25)]:
            original = analysis.probe.TAIL + '[' + field + ']'
            if field == 'id': original = 'i(' + original + ')'
            if field == 'vdsat': original = 'v(' + original + ')'
            values[original] = values[alias] = value
        point = dict(time_ns=10, p_v=0., n_v=.1, expected={
            'V(' + n + ')': values['v(' + n.replace(':', '.').lower() + ')'] for n in analysis.probe.NODES})
        return values, point

    def test_unit_wrapped_aliases_match_actual_model_parameters(self):
        values, point = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'point_0.raw').write_bytes(b'retained fixture')
            with patch.object(analysis.probe, 'read_raw', return_value=(list(values), np.array([list(values.values())]))):
                result = analysis.measurements(folder, [point])[0]
            self.assertAlmostEqual(result['power']['rails_mw'], 3.48)
            self.assertAlmostEqual(result['power']['reference_mw'], .24)
            self.assertEqual(result['tail']['vdsat'], .25)
            self.assertTrue(all(v == 0 for v in result['voltage_differences_from_transient_v'].values()))

    def test_inconsistent_missing_and_nonfinite_model_values_are_rejected(self):
        for kind in ['mismatch', 'missing', 'nonfinite', 'wrong_input']:
            values, point = self.fixture()
            if kind == 'mismatch': values['i(tail_id)'] *= 2
            if kind == 'missing': del values['v(tail_vdsat)']
            if kind == 'nonfinite': values['tail_gm'] = float('nan')
            if kind == 'wrong_input': values['v(p)'] = .2
            with self.subTest(kind=kind), patch.object(analysis.probe, 'read_raw', return_value=(list(values), np.array([list(values.values())]))):
                with self.assertRaises(ValueError): analysis.measurements(Path('/unused'), [point])


if __name__ == '__main__': unittest.main()
