# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import setup_convergence_observer_300_v1 as p
class Tests(unittest.TestCase):
 def test_actual_convergence_source_is_recoverable(self):
  source=next(p.PARENT.glob('*/src/maths/ni/niconv.c')).read_text()
  changed=p.instrument(source)
  self.assertEqual(p.strip(changed),source)
  self.assertEqual(changed.count('OLVDS_CONV'),2)
  self.assertIn('fabs(new-old)/tol',changed)
  with self.assertRaises(ValueError):p.instrument('unrelated')
 def test_diode_patch_does_not_touch_capacitance_or_mos(self):
  source=next(p.PARENT.glob('*/src/spicelib/devices/dio/dioload.c')).read_text()
  changed=p.diode_patch(source)
  a=source.splitlines();b=changed.splitlines()
  diff=[(x,y) for x,y in zip(a,b) if x!=y]
  self.assertEqual(len(diff),1)
  self.assertIn('deplchargeSW =',diff[0][0])
  self.assertIn('DIOtDepSWCap',diff[0][1])
  with self.assertRaises(ValueError):p.diode_patch(changed)
 def test_sidewall_integral_and_derivative_join(self):
  potential=.2;grading=.2;fcs=.4;cap=.25e-12;v=fcs*potential
  q=cap*potential*(1-(1-fcs)**(1-grading))/(1-grading)
  def low(x):return cap*potential*(1-(1-x/potential)**(1-grading))/(1-grading)
  def high(x):return q+cap/(1-fcs)**(1+grading)*((1-fcs*(1+grading))*(x-v)+grading/(2*potential)*(x*x-v*v))
  self.assertAlmostEqual(low(v),high(v),places=25)
  h=1e-7;expected=cap/(1-fcs)**grading
  self.assertLess(abs((high(v+h)-low(v-h))/(2*h)-expected)/expected,1e-6)
if __name__=='__main__':unittest.main()
