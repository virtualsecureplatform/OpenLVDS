# SPDX-License-Identifier: GPL-3.0-only
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_uniform_tree_v3 as pilot


class UniformPilotMeasurementTests(unittest.TestCase):
    def trace(self, folder, overshoot=False, missing=False, late=False, stuck=False):
        spec = pilot.specifications()[0]
        devices = [dict(name='XD:Xexample', terminals=['OUT', '0', 'VDD', 'XD:body'], limit_v=1.95)]
        t = np.arange(0., 20001., 10.)
        def pulse(delay):
            return sum(1.8*(np.clip((t-(base+2050+delay))/100, 0, 1)
                           - np.clip((t-(base+6050+delay))/100, 0, 1)) for base in (0, 10000))
        values = dict(time=t*1e-12)
        values.update({'v(in)': pulse(0), 'v(out)': np.zeros(len(t)) if stuck else pulse(100),
                       'v(vdd)': np.full(len(t), 1.8), 'v(xd.body)': np.zeros(len(t))})
        for pin, value in pilot.circuit.encode(0, 0).items():
            values['v('+pin.lower()+')'] = np.full(len(t), 1.8*value)
            i = int(pin[1:])
            if pin[0] == 'S':
                values[f'v(xd.select{i})'] = np.full(len(t), 1.8*value)
            else:
                values[f'v(xd.fine{i})'] = np.full(len(t), 1.8*value)
                values[f'v(xd.fine_b{i})'] = np.full(len(t), 1.8*(1-value))
        if overshoot:
            values['v(out)'][230] = 2.05
        if missing:
            del values['v(xd.body)']
        names = list(values)
        data = np.column_stack(list(values.values()))
        if late:
            data = data[1:]
        header = f'Title: test\nFlags: real\nNo. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'
        header += ''.join(f'{i} {n} voltage\n' for i, n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
        return spec, devices

    def test_complete_trace_reports_delays_and_remains_unqualified(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices = self.trace(folder)
            result = pilot.measure(folder, spec, devices)
            self.assertTrue(result['terminal_screen_passed'])
            self.assertTrue(result['control_settling_passed'])
            for sample in result['samples']:
                self.assertAlmostEqual(sample['rise_delay_ps'], 100)
                self.assertAlmostEqual(sample['fall_delay_ps'], 100)
            self.assertFalse(result['qualified_phy'])
            self.assertFalse(result['legal_code_table_admitted'])
            import json
            json.dumps(result, allow_nan=False)

    def test_voltage_failure_retained_as_electrical_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); spec, devices = self.trace(folder, overshoot=True)
            result = pilot.measure(folder, spec, devices)
            self.assertFalse(result['terminal_screen_passed'])
            self.assertAlmostEqual(result['terminal_stress'][0]['maximum_terminal_difference_v'], 2.05)

    def test_missing_terminal_late_start_and_missing_pulses_are_rejected(self):
        for option in ('missing', 'late', 'stuck'):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as d:
                folder = Path(d); spec, devices = self.trace(folder, **{option: True})
                with self.assertRaises(ValueError):
                    pilot.measure(folder, spec, devices)


if __name__ == '__main__':
    unittest.main()
