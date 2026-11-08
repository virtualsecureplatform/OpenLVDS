import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import clocking_profile_300 as p
class ProfileTests(unittest.TestCase):
    def test_budget_and_retained_precision(self):
        b=p.budgets();r=p.load()
        self.assertAlmostEqual(b['minimum_quarter_ps'],806.4516129032259)
        self.assertAlmostEqual(b['minimum_rx_span_ps'],3948.2758620689656)
        self.assertEqual(r['clocking']['timing']['period_error_ps'],20)
        self.assertEqual(r['clocking']['timing']['payload_margin_ps'],200)
        self.assertEqual(r['requirements']['temperatures_c'],[0,25,40])
    def test_pll_mode_and_capture_namespace(self):
        root=p.ROOT
        wrapper=(root/'examples/openlvds_openpll_300.v').read_text()
        self.assertIn(".FEEDBACK_DIVIDER(5'd12)",wrapper)
        self.assertIn('clk_serial',wrapper)
        bench=(root/'tb/tb_openpll_300.v').read_text()
        self.assertIn('build/openpll_300/clock.csv',bench)
        self.assertIn("16'd300",bench)
if __name__=='__main__':unittest.main()
