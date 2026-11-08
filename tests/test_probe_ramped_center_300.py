# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_ramped_center_300 as p

class RampedOriginTests(unittest.TestCase):
    def test_only_current_origin_and_library_location_change(self):
        original=(p.PARENT/'0/bench.cir').read_text();out=p.ROOT/'build/unused-small-origin/bank.spice'
        for offset in p.OFFSETS:
            text=p.deck(original,out,p.PARENT/'bank.spice',offset)
            restored=text.replace(p.CARD+'\n','',1).replace(str(out),str(p.PARENT/'bank.spice'))
            self.assertEqual(restored,original)
    def test_feedback_or_existing_offset_is_rejected(self):
        original=(p.PARENT/'0/bench.cir').read_text();out=p.ROOT/'build/unused-small-origin/bank.spice'
        for changed in (original+'\nFfeedback N 0 VDD 1\n',original+'\n* i(vdd) feedback\n',original+'\nI_BENCH_CURRENT_CENTER VDD 0 .001\n'):
            with self.assertRaises(ValueError):p.deck(changed,out,p.PARENT/'bank.spice',.001)
    def test_unbounded_offsets_and_supply_changes_are_rejected(self):
        original=(p.PARENT/'0/bench.cir').read_text();out=p.ROOT/'build/unused-small-origin/bank.spice'
        with self.assertRaises(ValueError):p.deck(original,out,p.PARENT/'bank.spice',1e-5)
        with self.assertRaises(ValueError):p.deck(original.replace('VDD VDD 0 1.8','VDD VDD 0 1.9'),out,p.PARENT/'bank.spice',.001)

    def test_dc_drift_is_rejected_even_inside_full_waveform_voltage_limit(self):
        from unittest.mock import patch
        import numpy as np
        t = np.linspace(0, 40e-9, 4001)
        def pulses(shift):
            knots = [(0., 0.)]
            for k in range(8):
                rise = 2.1e-9 + k / 310e6 + shift
                fall = rise + .6 / 310e6
                knots += [(rise-50e-12, 0.), (rise+50e-12, 1.8),
                          (fall-50e-12, 1.8), (fall+50e-12, 0.)]
            knots += [(40e-9, 0.)]
            return np.interp(t, *zip(*knots))
        names = ['time', 'v(in)', 'v(out)', 'v(float)']
        a = np.column_stack([t, pulses(0), pulses(100e-12), np.ones_like(t)])
        result = {key: False for key in p.reference.KEYS}
        result.update(current_downstream_250ps_slew_domain_passed=True,
                      terminal_stress=[], controls=[], programming_gates=[])
        for drift, admitted in ((0., True), (1e-6, False)):
            b = a.copy(); b[:, 3] += drift
            with patch.object(p, 'validate', side_effect=[(names, a), (names, b)]):
                proof = p.compare(Path('/unused/original'), Path('/unused/new'), result, result)
            self.assertLess(proof['maximum_all_vector_error_v'], .002)
            self.assertEqual(proof['dc_operating_point_preserved'], admitted)
            self.assertEqual(proof['passed'], admitted)
