# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phase_threshold_pair_v2 as threshold
import probe_phase_threshold_v2 as probe
import test_analog_conditioned_arbiter_v2 as frontend_test


class PhaseThresholdTests(unittest.TestCase):
    def test_matched_native_branches_expose_all_six_custom_devices(self):
        text,devices=threshold.circuit()
        self.assertEqual(len(devices),6)
        for suffix in ['r','f']:
            self.assertIn(f'node_{suffix} sky130_fd_sc_hd__buf_8',text)
            self.assertIn(f'XCUNIT{suffix} cap_{suffix} VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=2',text)
            self.assertIn(f'XCBASE{suffix} node_{suffix} VSS',text)
        self.assertTrue(all(d['length_um']==.15 for d in devices))

    def test_conditioning_precedes_threshold_paths_and_same_retained_arbiter(self):
        spec=dict(drive=1,swap=0,offset_ps=0,reference_slew_ps=20,feedback_slew_ps=200,positive_offset=1)
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            text=probe.fixture(Path('/context'),spec,threshold.circuit()[1])
        self.assertIn('XT RFAST FFAST POS RTH FTH VDD 0 phase_threshold_pair',text)
        self.assertIn('XD RTH FTH SW ARM QA QB VDD 0 tag_arbiter',text)
        self.assertNotIn('XD RFAST FFAST SW',text)
        self.assertIn('VPOS POS 0 1.8',text)
        self.assertIn('V(xt:cap_r)'.lower(),text.lower())
        self.assertIn('V(RTH) V(FTH) V(POS)\n.end',text)

    def test_zero_offset_sign_is_set_by_threshold_polarity_not_a_fake_time_delay(self):
        # The original frontend fixture supplies the real event/health waveform
        # model; append explicit threshold outputs and controls for this reader.
        import tempfile
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'0';folder.mkdir()
            names,w,spec=frontend_test.AnalogArbiterMeasurements().fixture(folder)
            r=w[:,names.index('v(rfast)')];f=w[:,names.index('v(ffast)')]
            names+=['v(rth)','v(fth)','v(pos)'];w=np.column_stack([w,r,f,np.ones(len(w))*1.8])
            spec.update(offset_ps=0,positive_offset=1)
            with patch.object(probe.base,'read_raw',return_value=(names,w)):
                result=probe.measure(folder,spec)
            self.assertEqual(result['expected_vote'],1)
            self.assertEqual(result['correct_sign_fraction'],1)
            self.assertTrue(result['frontend_stress_passed']);self.assertTrue(result['common_mode_passed'])
            self.assertFalse(result['detector_admitted'])
