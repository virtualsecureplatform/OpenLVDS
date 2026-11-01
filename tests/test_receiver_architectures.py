from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits,flatten
import receiver_architectures as a
from receiver_tail_headroom_experiment import source_variant

class ReceiverArchitectures(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.base=source_variant((Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text(),True)
 def test_bias_scaling_keeps_reference_ratio_and_all_other_devices(self):
  old=circuits(self.base)
  for scale in [2,4]:
   new=circuits(a.transform(self.base,'lvt_bias'+str(scale)))
   rows={r[0]:r for r in new[a.TOP][1]}
   self.assertEqual(rows['XCT'][3]['w'],str(16*scale));self.assertEqual(rows['XNCB'][3]['w'],str(2*scale))
   for row in old[a.TOP][1]:
    if row[0] not in ['XCT','XNCB','XC0','XC1']:self.assertEqual(rows[row[0]],row)
 def test_all_pmos_variants_isolate_thin_gates_from_high_voltage_decision_nodes(self):
  original=circuits(self.base)
  for variant in a.VARIANTS[3:]:
   defs=circuits(a.transform(self.base,variant));rows={r[0]:r for r in defs[a.TOP][1]}
   for name in ['XCT','XC0','XC1','XCD','XCM']:self.assertIn('g5v0d10v5',rows[name][2])
   self.assertEqual(rows['XCT'][1],['CT','PB','VDDIO','VDDIO'])
   self.assertEqual(rows['XIB0'][2],a.DOWN)
   self.assertEqual(defs[a.DOWN][0],['A','Y','VDDD','VSS'])
   for row in defs[a.DOWN][1]:self.assertIn('g5v0d10v5',row[2])
   for name in original:
    if name!=a.TOP:self.assertEqual(original[name],defs[name])
   for row in original[a.TOP][1]:
    if row[0] not in ['XCT','XC0','XC1','XCD','XCM','XIB0']:self.assertEqual(rows[row[0]],row)
   pins,devices=flatten(defs,a.TOP);self.assertEqual(pins,original[a.TOP][0]);self.assertTrue(devices)
 def test_unknown_or_modified_baselines_cannot_be_reinterpreted(self):
  with self.assertRaises(ValueError):a.transform(self.base,'unknown')
  for source in [self.base.replace('XNCB NBC NBC','XNCB NBC PP'),a.transform(self.base,'lvt')]:
   with self.assertRaises(ValueError):a.transform(source,'pmos_p8_t4')
