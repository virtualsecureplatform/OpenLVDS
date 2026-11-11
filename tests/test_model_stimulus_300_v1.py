# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import math
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from model_stimulus_300_v1 import smooth_inputs
import qualify_models_xyce_300_v2 as models


class ModelStimulus(unittest.TestCase):
    def test_fixed_rails_and_model_devices_preserved(self):
        before=models.deck(Path('/tmp/device-test'),'tt',25,'xyce')
        after=smooth_inputs(before)
        unchanged=lambda t:[line for line in t.splitlines() if not line.startswith(('VIN ','VIN33 ','BVIN ','BVIN33 '))]
        self.assertEqual(unchanged(before),unchanged(after))
        self.assertIn('V18 V18 0 1.8',after)
        self.assertIn('V33 V33 0 3.3',after)
        with self.assertRaises(ValueError):
            smooth_inputs(after)

    def test_actual_epochs_and_slews(self):
        after=smooth_inputs(models.deck(Path('/tmp/device-test'),'tt',25,'xyce'))
        source=next(line for line in after.splitlines() if line.startswith('BVIN '))
        expression=source.split('V={',1)[1][:-1]
        # Evaluate only our generated arithmetic fixture, with no builtins.
        def at(t):return eval(expression,{'__builtins__':{}},{'time':t,'tanh':math.tanh})
        for epoch,slew,up in [(1.0125e-9,20e-12,True),(2.5125e-9,20e-12,False),(4.15625e-9,250e-12,True),(5.65625e-9,250e-12,False)]:
            def crossing(level):
                lo,hi=epoch-slew*2,epoch+slew*2
                for _ in range(60):
                    mid=(lo+hi)/2
                    if (at(mid)<level)==up:lo=mid
                    else:hi=mid
                return (lo+hi)/2
            self.assertLess(abs(crossing(.9)-epoch),.01e-12)
            self.assertLess(abs(abs(crossing(1.62)-crossing(.18))-slew),.01e-12)


if __name__=='__main__':unittest.main()
