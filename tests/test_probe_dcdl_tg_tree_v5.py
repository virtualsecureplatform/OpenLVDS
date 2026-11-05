# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_tg_tree_v5 as pilot


class TGControlWaveformTests(unittest.TestCase):
    def fixture(self, folder, fault=False):
        spec = pilot.specifications()[0]
        time = np.arange(0., 20001., 10.)
        def pulses(delay):
            return sum(1.8*(np.clip((time-(base+2050+delay))/100, 0, 1)
                           - np.clip((time-(base+6050+delay))/100, 0, 1)) for base in (0, 10000))
        values = {'time': time*1e-12, 'v(in)': pulses(0), 'v(out)': pulses(100),
                  'v(vdd)': np.full(len(time), 1.8)}
        for pin, value in pilot.circuit.dimensions.encode(0, 0).items():
            values['v('+pin.lower()+')'] = np.full(len(time), 1.8*value)
        for node, value in pilot.circuit.control_targets(0, 0).items():
            values['v(xd.'+node.lower()+')'] = np.full(len(time), 1.8*value)
        if fault:
            values['v(xd.en0_0)'][:] = 0
        names = list(values)
        data = np.column_stack(list(values.values()))
        header = f'Title: test\nFlags: real\nNo. Variables: {len(names)}\nNo. Points: {len(time)}\nVariables:\n'
        header += ''.join(f'{i} {n} voltage\n' for i, n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
        devices = [dict(name='XD:example', terminals=['OUT', 'IN', '0', 'VDD'], limit_v=1.95)]
        return spec, devices

    def test_full_decoder_complement_controls_are_measured_and_remain_unqualified(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices = self.fixture(folder)
            result = pilot.measure(folder, spec, devices)
            self.assertTrue(result['onehot_control_settling_passed'])
            self.assertTrue(result['control_settling_passed'])
            self.assertFalse(result['qualified_phy'])
            self.assertFalse(result['electrical_qualification_passed'])
            self.assertFalse(result['physical_parasitics_retained'])
            json.dumps(result, allow_nan=False)

    def test_bad_decoder_is_rejected_despite_correct_external_word_and_fine_controls(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices = self.fixture(folder, fault=True)
            result = pilot.measure(folder, spec, devices)
            self.assertTrue(result['control_settling_passed'])
            self.assertFalse(result['onehot_control_settling_passed'])
            bad = [c for c in result['onehot_controls'] if not c['passed']]
            self.assertEqual([c['node'] for c in bad], ['en0_0'])


if __name__ == '__main__':
    unittest.main()
