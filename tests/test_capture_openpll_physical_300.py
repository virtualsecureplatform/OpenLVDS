import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import capture_openpll_physical_300 as p
class PhysicalEdgesTests(unittest.TestCase):
    def test_threshold_interpolation_retains_frequency_and_duty_without_rescaling(self):
        time=np.arange(0,70e-9,2e-12);voltage=.9+.9*np.sin(2*np.pi*300e6*time+.2)
        result=p.metrics(p.edges(time,voltage),p.load()['requirements'])
        self.assertTrue(result['passed']);self.assertAlmostEqual(result['frequency_mhz'],300.,places=5)
        self.assertAlmostEqual(result['duty_min'],.5,places=5)
    def test_flat_nonfinite_and_reverse_time_are_rejected(self):
        t=np.arange(100)*1e-12
        for time,values in [(t,np.zeros(100)),(t,np.full(100,np.nan)),(t[::-1],np.zeros(100))]:
            with self.assertRaises(ValueError):p.edges(time,values)
    def test_exact_threshold_samples_count_once(self):
        time=np.arange(400)*(1/300e6/4);voltage=np.tile([0.,.9,1.8,.9],100)
        result=p.metrics(p.edges(time,voltage),p.load()['requirements'])
        self.assertTrue(result['passed']);self.assertAlmostEqual(result['frequency_mhz'],300.)
    def test_digitalizing_small_or_unsafe_swing_is_rejected(self):
        time=np.arange(0,70e-9,2e-12)
        for voltage in [.9+.2*np.sin(2*np.pi*300e6*time),1.+1.1*np.sin(2*np.pi*300e6*time)]:
            with self.assertRaises(ValueError):p.edges(time,voltage)
    def test_partial_failure_is_retained_and_never_marked_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with self.assertRaisesRegex(RuntimeError,'waveform failed'):
                with p.recording(out):
                    (out/'partial.raw').write_bytes(b'partial')
                    raise RuntimeError('waveform failed')
            state=json.loads((out/'state.json').read_text())
            self.assertEqual(state['status'],'failed');self.assertFalse(state['qualified_phy'])
            self.assertEqual((out/'partial.raw').read_bytes(),b'partial')
