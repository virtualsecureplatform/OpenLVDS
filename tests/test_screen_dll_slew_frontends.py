from copy import deepcopy
import json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import screen_dll_slew_frontends as s

class SlewScreen(unittest.TestCase):
 def test_matrix_contains_both_fault_signs_and_zero_brackets_for_every_candidate(self):
  t=s.tasks();self.assertEqual(len(t),56);self.assertEqual(len({x['id'] for x in t}),56)
  for v in s.cal.CANDIDATES:
   for pair in s.SLEWS:
    self.assertEqual({x['spec']['offset_ps'] for x in t if x['variant']==v and (x['spec']['reference_slew_ps'],x['spec']['feedback_slew_ps'])==pair},set(s.OFFSETS))
 def test_incomplete_calibration_does_not_stage_any_candidate(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   with patch.object(s.cal,'bound',return_value={'tasks':[]}):
    with self.assertRaisesRegex(ValueError,'Complete calibration'):s.calibration_gate(root)
 def rows(self):
  return [dict(task=t['id'],variant=t['variant'],offset_ps=t['spec']['offset_ps'],slew=[t['spec']['reference_slew_ps'],t['spec']['feedback_slew_ps']],error=None,
       result=dict(passed=True,mean_power_w=.001,phase={'filtered_area_difference_v':t['spec']['offset_ps']*.0007})) for t in s.tasks()]
 def manifest(self):return {'identity':{'scope':'test','footprint_um2':{v:i+1 for i,v in enumerate(s.cal.CANDIDATES)}}}
 def test_false_bad_missing_case_or_unbalanced_response_disqualifies_candidate(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'manifest.json').write_text('{}');m=self.manifest();rows=self.rows()
   self.assertEqual(s.aggregate(p,m,rows)['ranked_survivors'],list(s.cal.CANDIDATES))
   rows[0]['result']['passed']=False
   self.assertNotIn(s.cal.CANDIDATES[0],s.aggregate(p,m,rows)['ranked_survivors'])
   rows=self.rows()
   for r in rows[:14]:r['result']['phase']['filtered_area_difference_v']+=.04
   self.assertNotIn(s.cal.CANDIDATES[0],s.aggregate(p,m,rows)['ranked_survivors'])
   self.assertNotIn(s.cal.CANDIDATES[0],s.aggregate(p,m,self.rows()[1:])['ranked_survivors'])
 def test_clock_missing_extra_edges_and_insufficient_swing_are_rejected(self):
  t=np.linspace(0,160e-9,16001);v=.9+.9*np.sin(2*np.pi*400e6*t)
  signals={n:v.copy() for n in ['REF','FDB','REF_FAST','FDB_FAST']}
  self.assertTrue(s.clock_integrity(t,signals))
  signals['REF_FAST'][:]=.9
  self.assertFalse(s.clock_integrity(t,signals))
  signals['REF_FAST']=.9+.9*np.sin(2*np.pi*800e6*t)
  self.assertFalse(s.clock_integrity(t,signals))
 def test_lef_area_uses_both_paths_and_all_gates(self):
  text='\n'.join('MACRO sky130_fd_sc_hd__'+n+'\n SIZE 2 BY 3 ;\nEND '+n for n in ['clkbuf_4','clkbuf_8','nor3_1','nor4_1','inv_4'])
  a=s.areas(text);self.assertEqual(a['clkbuf_4'],12);self.assertEqual(a['nor4_inv4'],24)
  with self.assertRaises(ValueError):s.areas('')
 def test_partial_screen_never_starts_spice(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'state.json').write_text('{}');(p/'manifest.json').write_text('{}')
   with patch.object(s,'bound',return_value={'tasks':[]}),patch.object(s,'lease') as lease:
    with self.assertRaisesRegex(ValueError,'no retry'):s.run(p)
    lease.assert_not_called()
