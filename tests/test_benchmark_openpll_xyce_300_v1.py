# SPDX-License-Identifier: GPL-3.0-only
import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark_openpll_xyce_300_v1 as b
import assess_openpll_xyce_300_v1 as assessment

def raw(path,names,data):
 header='Title: test\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: '+str(len(names))+'\nNo. Points: '+str(len(data))+'\nVariables:\n'
 header+=''.join(f'\t{k}\t{n}\t'+('time' if n=='time' else 'voltage')+'\n' for k,n in enumerate(names))
 path.write_bytes((header+'Binary:\n').encode()+np.asarray(data,dtype='<f8').tobytes())

class Tests(unittest.TestCase):
 def test_collector_rejects_live_producer_without_writing_assessment(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)
   for name,data in [('manifest.json',dict(identity={},tasks=[])),('summary.json',dict(rows=[])),('state.json',dict(status='running'))]:
    (p/name).write_text(json.dumps(data))
   with self.assertRaisesRegex(ValueError,'not terminal'):assessment.report(p)
   self.assertFalse((p/'assessment.json').exists())
 def test_comment_adapter_keeps_signed_physical_cards(self):
  text='R1 a b 0.003 $ annotation\nC1 a 0 -2e-18\nX1 a 0 cell w=1\n'
  self.assertEqual(b.library_adapter(text),'R1 a b 0.003\nC1 a 0 -2e-18\nX1 a 0 cell w=1\n')
 def test_timing_comparison_matches_names_and_interpolates_edges(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);t=np.arange(17)*1e-9;v=np.arange(17)%2*1.8
   raw(p/'ref',['time','v(in)','v(out)'],np.column_stack([t,v,v]))
   raw(p/'new',['time','v(out)','v(in)'],np.column_stack([t+.1e-12,v,v]))
   r=b.compare(p/'ref',p/'new',['time','v(in)','v(out)'],16e-9,True)
   self.assertTrue(r['all_eight_edges_each_direction']);self.assertAlmostEqual(r['maximum_crossing_error_ps'],.1,places=6)
   self.assertTrue(r['timing_screen_within_10ps'])
 def test_missing_output_pulse_is_retained_as_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);t=np.arange(17)*1e-9;v=np.arange(17)%2*1.8;missing=v.copy();missing[-3:]=0
   raw(p/'ref',['time','v(in)','v(out)'],np.column_stack([t,v,v]))
   raw(p/'new',['time','v(in)','v(out)'],np.column_stack([t,v,missing]))
   r=b.compare(p/'ref',p/'new',['time','v(in)','v(out)'],16e-9,True)
   self.assertFalse(r['all_eight_edges_each_direction']);self.assertFalse(r['timing_screen_within_10ps'])

if __name__=='__main__':unittest.main()
