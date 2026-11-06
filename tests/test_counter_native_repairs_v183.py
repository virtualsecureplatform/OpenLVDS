# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_counter_native_repairs_v183 as p


class NativeSetterCounterIntegration(unittest.TestCase):
    def test_only_low0_setter_is_retargeted_and_all_other_library_bytes_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            cells=f'.subckt {p.OLD} A_N B Y VGND VPWR\n.ends\n'
            module=f'.subckt pair CLK request_i low0_sn VGND VPWR\nXlow0_set_pair CLK request_i low0_sn VGND VPWR {p.OLD}\nXlow1_set_pair CLK request_i low0_sn VGND VPWR {p.OLD}\n.ends\n'
            (folder/'cells.spice').write_text(cells);(folder/'pair.spice').write_text(module)
            rc=f'.subckt {p.NEW} A_N B Y VGND VPWR\nR0 Y y0 .1\n.ends\n'
            newcells,newmodule=p.libraries(folder,rc)
            self.assertEqual(newcells,cells+'\n'+rc);self.assertEqual(newmodule.splitlines()[2],module.splitlines()[2])
            self.assertTrue(newmodule.splitlines()[1].endswith(p.NEW))
            with self.assertRaises(ValueError):p.libraries(folder,rc.replace('A_N B Y VGND VPWR','B A_N Y VGND VPWR'))
            (folder/'pair.spice').write_text(module.replace('Xlow0_set_pair CLK','Xlow0_set_pair wrong'))
            with self.assertRaises(ValueError):p.libraries(folder,rc)

    def test_full_native_fixture_keeps_new_setter_body_probe_and_original_stimulus(self):
        spec=p.source.source.source.specifications()[0]
        ds=[dict(name='XD:XR:Xlow0_set_pair:X0',model='sky130_fd_pr__nfet_01v8',limit_v=1.95,terminals=['XD:XR:Xlow0_set_pair:d.t0','XD:XR:Xlow0_set_pair:g.t1','0','XD:XR:Xlow0_set_pair:new_body.t2'])]
        before=p.source.fixture(Path('/fixture'),spec,ds);after=p.fixture(Path('/fixture'),spec,ds)
        self.assertEqual(before.splitlines()[1:],after.splitlines()[1:]);self.assertIn('.tran 1p 26n 0 1p',after)
        self.assertIn('V(XD:XR:Xlow0_set_pair:new_body.t2)',after)


if __name__=='__main__':unittest.main()
