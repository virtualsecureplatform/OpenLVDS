# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_dcc_xyce_300_v1 as campaign


class DccXyce300(unittest.TestCase):
    def test_complete_native_inventories_differ(self):
        for variant,expected in [('baseline',136),('inv8',144)]:
            donor = campaign.DONORS[variant]
            library = (donor/'cells.spice').read_text()+'\n'+(donor/'hold1.spice').read_text()
            text, observed = campaign.native_fixture(donor,campaign.specs()[0],library,variant)
            self.assertEqual(len(observed['devices']),expected)
            for d in observed['devices']:
                for node in d['terminals']:
                    if node!='0':
                        self.assertIn('v('+node.lower().replace(':','.')+')',text.lower().replace(':','.'))

    def test_interpolated_crossings_and_missing_pulse(self):
        names = ['time','v(q)']
        data = np.array([[0.,0.],[1.,1.8],[2.,0.],[3.,1.8]])
        np.testing.assert_array_equal(campaign.crossing_times(names,data,'q',True),[.5,2.5])
        np.testing.assert_array_equal(campaign.crossing_times(names,data,'q',False),[1.5])
        self.assertEqual(len(campaign.crossing_times(names,data[:2],'q',False)),0)

    def test_both_unequal_slew_directions_and_duties(self):
        specs = campaign.specs()
        self.assertEqual(len(specs),8)
        for duty in [.4,.6]:
            for a,b in [(20,250),(250,20),(20,20),(250,250)]:
                self.assertTrue(any(s['r_duty']==duty and s['r_slew_10_90_ps']==a and s['f_slew_10_90_ps']==b for s in specs))


if __name__=='__main__':
    unittest.main()
