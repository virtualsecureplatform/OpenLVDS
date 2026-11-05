# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_weighted_bank_rc_v2 as verification


class NativeBankVerificationAdmissionTests(unittest.TestCase):
    def test_partial_or_failed_native_extraction_cannot_be_verified_as_complete(self):
        report=dict(passed=True,rc_topology_passed=True,reduced_passivity_passed=True,
                    placement_check={'passed':True})
        verification.check_report(report,{'status':'bank_rc_complete'})
        for key in ['passed','rc_topology_passed','reduced_passivity_passed','placement_check']:
            for value in [False,None]:
                candidate=dict(report);candidate[key]=value if key!='placement_check' else {'passed':value}
                with self.subTest(check=key,value=value),self.assertRaises(ValueError):
                    verification.check_report(candidate,{'status':'bank_rc_complete'})
        for state in [{},{'status':'extracting'},{'status':'held_rc_failed'}]:
            with self.subTest(state=state),self.assertRaises(ValueError):verification.check_report(report,state)


if __name__=='__main__':unittest.main()
