# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_tg_terminated_v6 as pilot
from native_binary_raw_v2 import read
import test_probe_dcdl_tg_tree_v5 as fixture_source


class TerminatedTailWaveformTests(unittest.TestCase):
    def fixture(self, folder, minimum):
        fixture_source.TGControlWaveformTests().fixture(folder)
        names, mapped = read(folder/'bench.raw')
        # Close the mapping before replacing its synthetic fixture.
        data = np.array(mapped); del mapped
        tail = np.zeros(len(data)); tail[300] = minimum
        data = np.column_stack([data, tail]); names += ['v(xd.unused_tail)']
        header = f'Title: test\nFlags: real\nNo. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'
        header += ''.join(f'{i} {n} voltage\n' for i, n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
        devices = [dict(name='XD:Xtail_load:example', terminals=['XD:unused_tail', 'IN', 'VDD', 'VDD'], limit_v=1.95)]
        return pilot.specifications()[0], devices

    def test_tail_range_and_native_screen_remain_separate_from_phy_qualification(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices = self.fixture(folder, -.1)
            result = pilot.measure(folder, spec, devices)
            self.assertEqual(result['tail_output_minimum_v'], -.1)
            self.assertEqual(result['tail_termination_um'], [2, 2])
            self.assertTrue(result['terminal_screen_passed'])
            self.assertTrue(result['onehot_control_settling_passed'])
            self.assertFalse(result['qualified_phy'])
            self.assertFalse(result['electrical_qualification_passed'])
            json.dumps(result, allow_nan=False)

    def test_unused_tail_device_voltage_cannot_be_excluded_from_the_screen(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices = self.fixture(folder, -.16)
            result = pilot.measure(folder, spec, devices)
            self.assertFalse(result['terminal_screen_passed'])
            self.assertAlmostEqual(result['terminal_stress'][0]['maximum_terminal_difference_v'], 1.96)


if __name__ == '__main__':
    unittest.main()
