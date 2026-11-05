# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import measure_tg_component_rc_v8 as reader
from native_binary_raw_v2 import read
from run_native_binary_v2 import translate
import test_probe_dcdl_tg_component_rc_v7 as fixtures


class PassiveProbeRecoveryTests(unittest.TestCase):
    def fixture(self, folder, remove_active=False):
        spec, devices, gates = fixtures.DistributedGateWaveformTests().fixture(folder, 0)
        names, mapped = read(folder/'bench.raw')
        data = np.array(mapped); del mapped
        index = names.index('v(xd.unused_tail)')
        names[index] = 'v(xd.xtail_load.out.t0)'
        devices[0]['terminals'][0] = 'XD:Xtail_load:OUT.t0'
        if remove_active:
            data = np.delete(data, index, axis=1); names.pop(index)
        header = f'Title: test\nFlags: real\nNo. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'
        header += ''.join(f'{i} {n} voltage\n' for i, n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
        return spec, devices, gates

    def test_unsaved_passive_node_is_not_inferred_and_all_active_checks_are_retained(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices, gates = self.fixture(folder)
            result = reader.measure(folder, spec, devices, gates)
            self.assertFalse(result['public_tail_range_available'])
            self.assertIsNone(result['tail_output_minimum_v'])
            self.assertIsNone(result['tail_output_maximum_v'])
            self.assertTrue(result['terminal_screen_passed'])
            self.assertTrue(result['balancing_buffer_terminal_screen_passed'])
            self.assertTrue(result['distributed_control_settling_passed'])
            self.assertAlmostEqual(result['balancing_buffer_max_terminal_difference_v'], 1.9)
            self.assertFalse(result['qualified_phy'])
            json.dumps(result, allow_nan=False)

    def test_missing_active_terminal_is_still_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices, gates = self.fixture(folder, remove_active=True)
            with self.assertRaises(ValueError):
                reader.measure(folder, spec, devices, gates)

    def test_native_tail_devices_cannot_be_omitted_to_bypass_the_voltage_screen(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices, gates = self.fixture(folder)
            with self.assertRaises(ValueError):
                reader.measure(folder, spec, devices[1:], gates)

    def test_future_fixture_explicitly_saves_public_node_separated_by_real_resistors(self):
        spec = reader.producer.specifications()[0]
        devices = [dict(name='XD:Xtail_load:X0', terminals=['XD:Xtail_load:OUT.t0', 'IN', 'VDD', 'VDD'], limit_v=1.95)]
        with patch.dict('os.environ', {'PDK_ROOT': '/test/pdk'}):
            old = reader.producer.fixture(Path('/test/bank'), spec, devices)
        self.assertNotIn('V(XD:unused_tail)', old)
        new = reader.add_public_probes(old)
        self.assertIn('V(XD:unused_tail)', new)
        self.assertEqual(reader.add_public_probes(new), new)
        self.assertEqual(new.replace(' V(XD:unused_tail)', '', 1), old)
        _, vectors = translate(new)
        self.assertIn('v(xd.unused_tail)', vectors)
        self.assertIn('v(xd.xtail_load.out.t0)', vectors)


if __name__ == '__main__':
    unittest.main()
