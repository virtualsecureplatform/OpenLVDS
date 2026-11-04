# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
import probe_phase_prefix_v2 as short
import test_analog_conditioned_arbiter_v2 as fixtures


class QuiescentPrefixTests(unittest.TestCase):
    def test_fixture_changes_only_pulse_origins_and_stop_time(self):
        spec=dict(drive=1,swap=0,offset_ps=-20,reference_slew_ps=100,feedback_slew_ps=100,positive_offset=0,settle_ps=20000)
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            before=short.parent_source.parent_source.fixture(Path('/context'),spec,[])
            after=short.fixture(Path('/context'),spec,[])
        self.assertIn('VARM ARM 0 PULSE(0 1.8 21n 20p 20p 5.98n 10n)',after)
        self.assertIn('VR R 0 PULSE(0 1.8 22n 0.1n 0.1n 1.15n 10n)',after)
        self.assertIn('.tran 1p 62n 0 1p',after)
        self.assertEqual(before.split('VPOS')[1],after.split('VPOS')[1].replace('.tran 1p 62n','.tran 1p 242n'))

    def test_explicit_time_origin_keeps_long_analyzer_metrics_and_short_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'0';folder.mkdir()
            names,w,spec=fixtures.AnalogArbiterMeasurements().fixture(folder)
            r=w[:,names.index('v(rfast)')];f=w[:,names.index('v(ffast)')]
            names+=['v(rth)','v(fth)','v(pos)'];w=np.column_stack([w,r,f,np.ones(len(w))*1.8])
            spec.update(offset_ps=0,positive_offset=1)
            devices=json.loads((folder.parent/'manifest.json').read_text())['tasks'][0]['devices']
            with patch.object(short.base,'read_raw',return_value=(names,w)):
                old=short.parent_source.measure(folder,spec)
                long=short.analysis.measure(folder,dict(spec=dict(spec,settle_ps=200000),devices=devices))
            for key in old:
                if key in long and key not in ['scope','version']:self.assertEqual(old[key],long[key],key)
            # Synthetic test waveform only: moving the origin must not change
            # actual tag votes, deltas or device stress measurement windows.
            select=w[:,0]>=180e-9;short_wave=w[select].copy();short_wave[:,0]-=180e-9
            with patch.object(short.base,'read_raw',return_value=(names,short_wave)):
                result=short.analysis.measure(folder,dict(spec=dict(spec,settle_ps=20000),devices=devices))
            self.assertEqual(result['votes'],long['votes'])
            np.testing.assert_allclose(result['threshold_feedback_minus_reference_ps'],long['threshold_feedback_minus_reference_ps'],atol=1e-8)
            self.assertTrue(result['frontend_stress_passed']);self.assertTrue(result['common_mode_passed'])
            self.assertFalse(result['detector_admitted'])
