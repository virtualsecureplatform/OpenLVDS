import sys,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import calibrate_dll_slew_bench as c

PDK='\n'.join('.subckt sky130_fd_sc_hd__'+name+' '+' '.join(ports)+'\nR0 A VGND 1\n.ends' for name,ports in [
 ('buf_4',['A','VGND','VNB','VPB','VPWR','X']),('clkbuf_4',['A','VGND','VNB','VPB','VPWR','X']),
 ('clkbuf_8',['A','VGND','VNB','VPB','VPWR','X']),('nor3_1',['A','B','C','VGND','VNB','VPB','VPWR','Y']),
 ('nor4_1',['A','B','C','D','VGND','VNB','VPB','VPWR','Y']),('inv_4',['A','VGND','VNB','VPB','VPWR','Y'])])

class SlewBench(unittest.TestCase):
 def test_all_four_candidates_use_named_ports_and_correct_polarity_chain(self):
  for v in c.CANDIDATES:
   s=c.conditioner(PDK,v);self.assertIn('.subckt lvds_slew_conditioner A VGND VNB VPB VPWR X',s)
   if v.startswith('nor'):
    count=int(v[3]);self.assertIn('XG0 '+' '.join(['A']*count)+' VGND VNB VPB VPWR MID',s)
    self.assertIn('XG1 MID VGND VNB VPB VPWR X sky130_fd_sc_hd__inv_4',s)
   else:self.assertIn('XG0 A VGND VNB VPB VPWR X sky130_fd_sc_hd__'+v,s)
 def test_unknown_candidate_or_changed_pdk_interface_rejected(self):
  with self.assertRaises(ValueError):c.conditioner(PDK,'another')
  with self.assertRaises(ValueError):c.conditioner(PDK.replace(' A B C D ',' A B C Z '),'nor4_inv4')
 def test_no_vcdl_or_ota_in_isolation_library(self):
  n='.subckt lvds_pfd A B\nR0 A B 1\n.ends\n.subckt lvds_bias A B\nR0 A B 1\n.ends\n.subckt UNUSED A B\n.ends'
  s='.subckt screen_bias A B\nR0 A B 1\n.ends\n.subckt lvds_phase_area A B\nR0 A B 1\n.ends\n.subckt lvds_phase_ota A B\n.ends'
  result=c.fast_library(n,s);self.assertNotIn('UNUSED',result);self.assertNotIn('lvds_phase_ota',result)
 def test_partial_outputs_are_never_restarted(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'state.json').write_text('{}')
   with patch.object(c,'bound',return_value={'tasks':[]}),patch.object(c,'lease') as lease:
    with self.assertRaisesRegex(ValueError,'no retry'):c.run(p)
    lease.assert_not_called()
 def test_engine_runtime_required(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'log';p.write_text('Total elapsed time (seconds) = 10.5');self.assertEqual(c.elapsed(p),10.5)
   p.write_text('partial')
   with self.assertRaises(ValueError):c.elapsed(p)
