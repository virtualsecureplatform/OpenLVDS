# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import detector_inputs_300_v1 as p


class DetectorInputTests(unittest.TestCase):
    def test_complete_900_point_matrix_and_true_slew_offset_width(self):
        specs=p.specifications();self.assertEqual(len(specs),900)
        self.assertEqual(len({json.dumps(s,sort_keys=True) for s in specs}),900)
        for s in specs:
            epochs=[]
            for phase in ('R','F'):
                rows=p.points(s,phase);up=[t for t,v in rows if abs(v-.18)<1e-12]
                high=[t for t,v in rows if abs(v-1.62)<1e-12]
                middle=[t for t,v in rows if abs(v-.9)<1e-12]
                self.assertEqual(len(up),8);self.assertEqual(len(high),8);self.assertEqual(len(middle),8)
                slew=s['reference_slew_ps' if phase=='R' else 'feedback_slew_ps']
                for k in range(4):
                    self.assertAlmostEqual(high[2*k]-up[2*k],slew)
                    self.assertAlmostEqual(up[2*k+1]-high[2*k+1],slew)
                    self.assertAlmostEqual(middle[2*k+1]-middle[2*k],1250)
                epochs.append(middle[::2])
            np.testing.assert_allclose(np.array(epochs[1])-epochs[0],s['offset_ps'],atol=1e-10)

    def test_independent_formula_matches_all_waveform_vertices_and_samples(self):
        for s in p.specifications()[:60]:
            for phase in ('R','F'):
                t=np.unique(np.r_[np.arange(0,62001,7),[x for x,v in p.points(s,phase)]])
                np.testing.assert_allclose(p.evaluate(t,s,phase),p.evaluate(t,s,phase,True),atol=1e-11)

    def test_real_fixture_preserves_noninput_circuit_and_capture(self):
        parent=p.donor.ROOT/'build/diagnostics/phase_threshold_pvt_v2/7f2eeea8cd9e0678'
        devices=json.loads((parent/'manifest.json').read_text())['tasks'][0]['devices']
        s=p.specifications()[0];original=p.donor.fixture(Path('test-detector'),s,devices)
        new=p.fixture(Path('test-detector'),s,devices)
        def keep(text):
            lines=text.splitlines();result=[];in_pwl=False
            for line in lines[1:]:
                if line.startswith(('VR R ','VF F ')):in_pwl='PWL(' in line;continue
                if in_pwl:
                    if line=='+ )':in_pwl=False
                    continue
                result.append(line)
            return result
        self.assertEqual(keep(original),keep(new))
        self.assertIn('.tran 1p 62n 0 1p',new)
        self.assertIn('VARM ARM 0 PULSE',new)
        with self.assertRaises(ValueError):p.points(dict(s,settle_ps=0),'R')
