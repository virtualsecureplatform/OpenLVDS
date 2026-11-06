# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_xyce_measured_joint_zero_v157 as p


class ExploratoryJointZeroTests(unittest.TestCase):
    def test_positive_candidate_result_can_never_admit_native_zero_or_backend(self):
        source=dict(joint_rc_zero_screen_passed=True,qualified_phy=True,electrical_qualification_passed=True,
                    whole_bank_rc_retained=True,samples=[dict(rise_delay_ps=500,fall_delay_ps=550)]*2)
        result=p.exploratory(source)
        self.assertTrue(result['exploratory_zero_screen_passed']);self.assertTrue(source['qualified_phy'])
        for flag in ('joint_rc_zero_screen_passed','native_zero_admitted','backend_qualified','model_equivalence_proven','qualified_phy','electrical_qualification_passed'):
            self.assertFalse(result[flag])
        self.assertEqual(result['samples'],source['samples']);self.assertTrue(result['whole_bank_rc_retained'])
        self.assertFalse(p.exploratory(dict(source,joint_rc_zero_screen_passed=False))['exploratory_zero_screen_passed'])

    def test_full_native_fixture_is_preserved_except_backend_output_and_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);parent=root/'native';out=root/'xyce';(parent/'0').mkdir(parents=True)
            ports=['IN','OUT',*[f'S{k}' for k in range(4)],*[f'E{k}' for k in range(31)],'VPWR','VGND']
            i=dict(spec=p.golden.spec('b2'),top='bank',ports=ports,model='/model.lib',observations=dict(devices=[dict(terminals=['XD:drain.t0','XD:gate.t1','0','VDD'])],controls=[dict(node='XD:control.t2',control='fine0')]))
            original=p.golden.fixture(parent,i);(parent/'0/bench.cir').write_text(original)
            actual=p.fixture(parent,out,i)
            restored=actual.replace('OpenLVDS '+p.VERSION,'OpenLVDS '+p.golden.VERSION,1).replace(str(out/'bank.spice'),str(parent/'bank.spice')).replace('.print tran format=raw file=bench.xyce.raw ','.print tran ')
            self.assertEqual(restored,original);self.assertEqual((parent/'0/bench.cir').read_text(),original)
            self.assertIn('.tran 2p 20n 0 2p',actual)
            self.assertIn('V(XD:gate.t1)',actual)
            (parent/'0/bench.cir').write_text(original+'* changed\n')
            with self.assertRaises(ValueError):p.fixture(parent,out,i)


if __name__=='__main__':unittest.main()
