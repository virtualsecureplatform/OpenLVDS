# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_qualification_measurements import marker_latency, compare
from qualify_dll_candidate import clock_wave, loop_fixture


class DLLQualification(unittest.TestCase):
    def trace(self, alias=False, omit=True):
        t = np.arange(0, 80e-9, 2e-12)
        period = 2.5e-9
        channels = []
        for i in range(5):
            delay = i*.625e-9 + (2.5e-9 if alias and i else 0)
            phase = (t-5e-9-delay)/period
            cycle = np.floor(phase).astype(int)
            v = 1.8*((phase % 1 < .5) & (cycle >= 0) & ((cycle != 6) if omit else True))
            channels.append(v)
        wave = np.column_stack([np.arange(len(t)), t, *channels])
        header = {f'V({n})':i+2 for i,n in enumerate(['PH0','PH90','PH180','PH270','FB'])}
        return wave, header

    def test_missing_pulse_records_unwrapped_delay(self):
        result = marker_latency(*self.trace(), 400, 20)
        self.assertTrue(result['passed'], result)
        for delay in result['unwrapped_sections_ps']:
            self.assertAlmostEqual(delay, 625, delta=3)

    def test_periodic_phase_alias_and_missing_marker_fail(self):
        self.assertFalse(marker_latency(*self.trace(alias=True), 400, 20)['passed'])
        self.assertFalse(marker_latency(*self.trace(omit=False), 400, 20)['passed'])

    def test_comparison_rejects_timing_error_and_truncated_intervals(self):
        a, h = self.trace()
        self.assertTrue(compare(a, h, a, h, list(n[2:-1] for n in h), 10, 50)['passed'])
        b = a.copy()
        b[:,1] += 30e-12
        self.assertFalse(compare(a, h, b, h, ['PH0'], 10, 50)['passed'])
        self.assertFalse(compare(a[:100], h, a[:100], h, ['PH0'], 10, 50)['passed'])

    def test_fixture_has_marker_after_unchanged_settled_window(self):
        body, probes, stop, timing = loop_fixture(dict(mhz=400, duty=.5, architecture='averaged_pfd_ota'))
        self.assertEqual((timing['start_ns'], timing['end_ns']), (1200, 1500))
        self.assertEqual(timing['marker_ns'], 1600)
        self.assertGreater(stop, timing['marker_ns']+10)
        self.assertIn('CTRL', probes)
        self.assertIn('C90 PH90 0 40f', body)

    def test_frequency_step_marker_is_on_an_actual_final_frequency_edge(self):
        for mhz in [390,410]:
            body, probes, stop, timing = loop_fixture(dict(mhz=400, duty=.5,
                step_mhz=mhz, architecture='averaged_pfd_ota'))
            self.assertLess(abs(timing['marker_ns']-2600), 1000/mhz/2)
            count = (timing['marker_ns']-1100)/(1000/mhz)
            self.assertAlmostEqual(count, round(count), places=6)


if __name__ == '__main__':
    unittest.main()
