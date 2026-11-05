# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_tg_component_rc_v7 as pilot
from native_binary_raw_v2 import read
import test_probe_dcdl_tg_terminated_v6 as fixtures


class DistributedGateWaveformTests(unittest.TestCase):
    def fixture(self, folder, value):
        spec, devices = fixtures.TerminatedTailWaveformTests().fixture(folder, -.1)
        names, mapped = read(folder/'bench.raw')
        data = np.array(mapped); del mapped
        data = np.column_stack([data, np.full(len(data), value)])
        names += ['v(xd.xfine_unit0.en.t0)']
        header = f'Title: test\nFlags: real\nNo. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'
        header += ''.join(f'{i} {n} voltage\n' for i, n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
        devices.append(dict(name='XD:Xfine_unit0:X3', terminals=['OUT', 'XD:Xfine_unit0:EN.t0', '0', '0'], limit_v=1.95))
        gates = [dict(device='XD:Xfine_unit0:X3', gate_node='XD:Xfine_unit0:EN.t0',
                      control_node='XD:fine0', bit=0, kind='fine')]
        return spec, devices, gates

    def test_actual_local_gate_is_observed_with_physical_scope_kept_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices, gates = self.fixture(folder, 0)
            result = pilot.measure(folder, spec, devices, gates)
            self.assertTrue(result['distributed_control_settling_passed'])
            self.assertTrue(result['control_settling_passed'])
            self.assertTrue(result['component_parasitics_retained'])
            self.assertFalse(result['whole_bank_rc_retained'])
            self.assertFalse(result['qualified_phy'])

    def test_wrong_local_gate_cannot_hide_behind_correct_public_pin_or_safe_mos_voltage(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices, gates = self.fixture(folder, .2)
            result = pilot.measure(folder, spec, devices, gates)
            self.assertTrue(result['public_control_settling_passed'])
            self.assertTrue(result['terminal_screen_passed'])
            self.assertFalse(result['distributed_control_settling_passed'])
            self.assertFalse(result['control_settling_passed'])
            self.assertAlmostEqual(result['distributed_fine_controls'][0]['maximum_deviation_v'], .2)


if __name__ == '__main__':
    unittest.main()
