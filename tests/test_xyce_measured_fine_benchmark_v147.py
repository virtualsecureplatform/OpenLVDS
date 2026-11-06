# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark_xyce_measured_fine_v147 as p


class XyceMeasuredFineBenchmarkTests(unittest.TestCase):
    def test_fixture_preserves_original_model_stimulus_and_only_changes_output_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp)/'gold';out=Path(temp)/'candidate';(parent/'0').mkdir(parents=True)
            i=dict(spec=dict(p.golden.zero.spec(),profile='b2',fine=31),model='/pdk/model.lib',ports=['IN','OUT','VPWR','VGND'],observations=dict(devices=[],controls=[]))
            original=p.golden.fixture(parent,i);(parent/'0/bench.cir').write_text(original)
            candidate=p.fixture(parent,out,i)
            recovered=candidate.replace('OpenLVDS '+p.VERSION,'OpenLVDS '+p.golden.VERSION,1).replace('.print tran format=raw file=bench.xyce.raw ','.print tran ',1).replace(str(out/'bank.spice'),str(parent/'bank.spice'))
            self.assertEqual(recovered,original);self.assertEqual((parent/'0/bench.cir').read_text(),original)
            self.assertIn('.tran 2p 20n 0 2p',candidate)

    def test_one_case_timing_agreement_or_missing_slew_never_qualifies_a_backend(self):
        result=dict(samples=[dict(rise_delay_ps=690.,fall_delay_ps=850.)]*2,maximum_output_slew_ps=244.,static_native_screen_passed=True,output_slew_domain_passed=True)
        r=p.compare(result,result,10.,100.)
        self.assertEqual(r['recorded_wall_time_ratio_ngspice_over_xyce'],10.)
        self.assertFalse(r['backend_qualified']);self.assertFalse(r['model_equivalence_proven']);self.assertFalse(r['standardized_performance_benchmark'])
        missing=dict(result,maximum_output_slew_ps=None,output_slew_domain_passed=False)
        self.assertIsNone(p.compare(missing,result,10.,100.)['maximum_output_slew_difference_ps'])


if __name__=='__main__':unittest.main()
