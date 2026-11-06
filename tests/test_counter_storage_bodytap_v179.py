# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_counter_storage_bodytap_v179 as p


class NativeStorageCounterIntegration(unittest.TestCase):
    def test_only_low0_storage_model_changes_and_old_library_stays_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);(parent/'guard_3').mkdir()
            cells=f'.subckt {p.OLD} A B Y VGND VPWR\n.ends\n'
            module=f'.subckt pair low0_sn low0_qb low0 VGND VPWR\nXlow0_q low0_sn low0_qb low0 VGND VPWR {p.OLD}\nXlow0_b low0_sn low0_qb low0 VGND VPWR {p.OLD}\n.ends\n'
            (parent/'guard_3/cells.spice').write_text(cells);(parent/'guard_3/pair.spice').write_text(module)
            rc=f'.subckt {p.NEW} A B Y VGND VPWR\nRnew Y y0 .1\nXn y0 A VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15\n.ends\n'
            newcells,newmodule=p.libraries(parent,rc)
            self.assertEqual(newcells,cells+'\n'+rc)
            self.assertEqual(newmodule.splitlines()[2],module.splitlines()[2])
            self.assertEqual(newmodule.splitlines()[1],module.splitlines()[1][:-len(p.OLD)]+p.NEW)
            with self.assertRaises(ValueError):p.libraries(parent,rc.replace('A B Y VGND VPWR','A B Y VPWR VGND'))
            (parent/'guard_3/pair.spice').write_text(module.replace('Xlow0_q low0_sn','Xlow0_q other'))
            with self.assertRaises(ValueError):p.libraries(parent,rc)

    def test_complete_fixture_retains_new_rc_body_probe_and_all_original_stimuli(self):
        spec=p.source.source.specifications()[0]
        observations=[dict(name='XD:XR:Xlow0_q:X0',model='sky130_fd_pr__nfet_01v8',limit_v=1.95,
                           terminals=['XD:XR:Xlow0_q:d.t0','XD:XR:Xlow0_q:g.t1','0','XD:XR:Xlow0_q:body_new.t7'])]
        root=Path('/fixture');old=p.source.fixture(root,spec,observations);new=p.fixture(root,spec,observations)
        self.assertEqual(old.splitlines()[1:],new.splitlines()[1:]);self.assertIn('OpenLVDS '+p.VERSION,new)
        self.assertIn('.tran 1p 26n 0 1p',new)
        self.assertIn('V(XD:XR:Xlow0_q:body_new.t7)',new)


if __name__=='__main__':unittest.main()
