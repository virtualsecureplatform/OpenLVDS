# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import extract_dcdl_bank_rc_v2 as bank_rc


class WholeBankRcAdmissionTests(unittest.TestCase):
    def test_success_flag_does_not_waive_drc_lvs_or_missing_signoff_metrics(self):
        keys=['route__drc_errors','magic__drc_error__count','klayout__drc_error__count',
              'design__lvs_error__count','antenna__violating__nets','antenna__violating__pins']
        with tempfile.TemporaryDirectory() as tmp,patch.object(bank_rc.physical,'bound',return_value={}):
            parent=Path(tmp)
            for key in keys:
                for value in [1,None]:
                    metrics=dict.fromkeys(keys,0)
                    if value is None:metrics.pop(key)
                    else:metrics[key]=value
                    (parent/'summary.json').write_text(json.dumps(dict(physical_implementation_passed=True,
                        interface_verified=True,returncode=0,metrics=metrics)))
                    with self.assertRaisesRegex(ValueError,'clean whole-bank physical signoff'):bank_rc.parent_files(parent)

    def test_power_checker_requires_both_connected_nets_and_successful_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            def run(argv,stdout,stderr):
                stdout.write('[INFO] All shapes on net VPWR are connected.\nGRID_CHECKED VPWR\nGRID_CHECKED VGND\n')
                return type('Result',(),dict(returncode=0))()
            with patch.object(bank_rc.subprocess,'run',side_effect=run):
                self.assertFalse(bank_rc.power_grid(out,out/'final.odb'))


if __name__=='__main__':unittest.main()
