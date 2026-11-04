# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_clock_components_v3 as components


class StrongNativeClockTests(unittest.TestCase):
    def test_logical_connections_and_async_clear_are_preserved(self):
        before=components.release.gates();after=components.strengthen(before)
        self.assertEqual([(n,p) for n,_,p in before],[(n,p) for n,_,p in after])
        self.assertEqual(sum(k=='nand3_2' and p['C']=='REQUEST' for _,k,p in after),4)
        self.assertFalse(any(k in ['inv_1','nand2_2'] for _,k,_ in after))

    def test_each_parallel_driver_is_an_actual_rc_instance_with_its_own_shunts(self):
        rc={components.CLOCK_BUFFER:dict(info=dict(ports=['A','X','VGND','VPWR']))}
        text=components.clean_source(rc,3)
        self.assertEqual(sum(l.startswith('Xclean') for l in text.splitlines()),6)
        self.assertEqual(sum(l.startswith('Xmonitor') for l in text.splitlines()),2)
        self.assertIn('Xclean0_2 F0 P0 VGND VPWR '+components.CLOCK_BUFFER,text)
        with self.assertRaises(ValueError):components.clean_source(rc,0)


if __name__=='__main__':unittest.main()
