# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_architecture_rate import observed_devices, measure
import receiver_architecture_observations as observed

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureRateObservations(unittest.TestCase):
    def source(self):
        base = observed.experiment.source_variant((ROOT/'analog/openlvds.spice').read_text(), False)
        return observed.instrument(base, 'pmos_p8_t4')

    def test_restorers_and_decision_devices_are_mapped_to_real_probes(self):
        devices = observed_devices(self.source())
        self.assertEqual(len(devices), 12)
        self.assertEqual(devices['XCT'][1][0], 'OBS_TAIL_D')
        self.assertEqual(devices['XIB0/XP'][1], ['RESTORE0', 'CO', 'VDDD', 'VDDD'])
        self.assertEqual(devices['XIB2/XN'][1], ['Q', 'RESTORE1', 'VSS', 'VSS'])
        with self.assertRaises(ValueError):
            observed_devices(self.source().replace('VOBS_TAIL CT OBS_TAIL_D 0', 'VOBS_TAIL CT OBS_TAIL_D 0.01'))

    def test_stress_peak_outside_rate_scoring_window_is_still_rejected(self):
        names = ['XR:XCORE:RESTORE0', 'XR:XCORE:CO', 'XR:XCORE:OBS_ITAIL', 'XR:XCORE:OBS_IREPLICA']
        headers = {'INDEX': 0, 'TIME': 1, **{'V('+n+')': i+2 for i, n in enumerate(names)}}
        wave = np.zeros((3, 6)); wave[:, 1] = [0, 30e-9, 60e-9]
        wave[:, 2] = .9; wave[:, 3] = [2.05, 1.8, 1.8]
        device = ('X', ['RESTORE0', 'CO', 'VSS', 'VSS'], 'sky130_fd_pr__nfet_01v8', {})
        result = measure(wave, headers, {'X': device})
        self.assertFalse(result['observed_thin_guard_passed'])
        self.assertEqual(result['devices']['X']['maximum_terminal_difference']['time_ns'], 0.)


if __name__ == '__main__':
    unittest.main()
