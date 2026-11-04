# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dcc_recovery_metrics_v2 import PHYSICAL_KEYS,physical_clean,explicit_metrics


class PhysicalRecoveryMetricTests(unittest.TestCase):
    def test_nonfinite_timing_is_preserved_without_fabricating_zero_slack(self):
        original=dict(physical=0,timing=dict(setup=float('inf'),hold=float('-inf'),unknown=float('nan')))
        result,nonfinite=explicit_metrics(original)
        self.assertEqual(nonfinite,{'/timing/setup':'Infinity','/timing/hold':'-Infinity','/timing/unknown':'NaN'})
        self.assertEqual(result['timing']['setup'],dict(nonfinite='Infinity'))
        self.assertEqual(result['physical'],0)
        json.dumps(result,allow_nan=False)
        self.assertEqual(original['timing']['setup'],float('inf'))

    def test_every_physical_gate_requires_a_finite_numeric_zero(self):
        metrics=dict.fromkeys(PHYSICAL_KEYS,0)
        self.assertTrue(physical_clean(metrics))
        for bad in [float('nan'),float('inf'),-1,1,False,'0',None]:
            self.assertFalse(physical_clean(dict(metrics,**{PHYSICAL_KEYS[0]:bad})))
        self.assertFalse(physical_clean({}))
