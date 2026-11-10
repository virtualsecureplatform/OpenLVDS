# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_convergence_cause_300_v1 as p
class Tests(unittest.TestCase):
 def test_direct_failure_values_and_worst_node_are_retained(self):
  text='OLVDS_STEP kind=ni_limit t=1e-12\nOLVDS_STEP kind=noncon_reject t=1e-12\n'
  text+='OLVDS_CONV t=1e-12 dt=1e-15 node=vdd#branch type=4 old=1e-10 new=2e-10 delta=1e-10 tolerance=1e-12 ratio=100\n'
  text+='OLVDS_CONV t=2e-12 dt=1e-15 node=vdd#branch type=4 old=1e-10 new=3e-10 delta=2e-10 tolerance=1e-12 ratio=200\n'
  r=p.analyze_log(text)
  self.assertEqual(r['convergence_failures_logged'],2)
  self.assertEqual(r['counts']['ni_limit'],1)
  self.assertEqual(r['counts']['noncon_reject'],1)
  self.assertEqual(float(r['worst_by_node']['vdd#branch']['ratio']),200)
  self.assertFalse(r['logging_cap_possible'])
 def test_no_log_does_not_invent_a_cause(self):
  r=p.analyze_log('normal simulator output')
  self.assertEqual(r['worst_by_node'],{})
  self.assertEqual(r['convergence_failures_logged'],0)
if __name__=='__main__':unittest.main()
