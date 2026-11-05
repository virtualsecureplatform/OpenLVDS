# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import signoff_weighted_bank_v2 as signoff


class WholeBankPhysicalAdmissionTests(unittest.TestCase):
    def test_route_success_does_not_replace_full_gds_connectivity_xor_or_lvs(self):
        metrics={k:0 for k in signoff.ZERO_METRICS}
        self.assertTrue(signoff.physical_pass(0,True,{'passed':True},metrics))
        for key in signoff.ZERO_METRICS:
            missing=dict(metrics);missing.pop(key)
            failed=dict(metrics);failed[key]=1
            with self.subTest(metric=key):
                self.assertFalse(signoff.physical_pass(0,True,{'passed':True},missing))
                self.assertFalse(signoff.physical_pass(0,True,{'passed':True},failed))
        for rc,target,check in [(1,True,{'passed':True}),(0,False,{'passed':True}),
                                 (0,True,{'passed':False}),(0,True,None)]:
            self.assertFalse(signoff.physical_pass(rc,target,check,metrics))

    def test_every_nested_initial_view_is_bound_and_missing_views_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'view';p.write_text('actual initial view')
            self.assertEqual(signoff.referenced_files({'odb':str(p),'sdf':{'corner':str(p)},'gds':None}),[p,p])
            for bad in ['relative.odb',str(p.with_name('missing')),{'corner':str(p.with_name('missing'))},17]:
                with self.subTest(view=bad),self.assertRaises(ValueError):signoff.referenced_files(bad)


if __name__=='__main__':unittest.main()
