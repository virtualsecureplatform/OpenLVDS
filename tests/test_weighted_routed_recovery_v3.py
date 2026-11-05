# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from recover_weighted_routed_v3 import check_failure,terminal_metadata
from test_weighted_routed_measurement_v3 import fixture


class RoutedRecoveryTests(unittest.TestCase):
    def test_only_the_recorded_terminal_reporting_failure_can_be_recovered(self):
        log='probe_weighted_routed_v2.py\nTypeError: Object of type bool is not JSON serializable'
        check_failure(log,dict(status='held_for_diagnosis'))
        for text,state in [(log,dict(status='running')),(log.replace('bool','ndarray'),dict(status='held_for_diagnosis')),
                           (log.replace('probe_weighted_routed_v2.py','another.py'),dict(status='held_for_diagnosis'))]:
            with self.assertRaises(ValueError):check_failure(text,state)

    def test_complete_raw_count_and_terminal_solver_success_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);fixture(p);(p/'console.log').write_text('Batch mode\n')
            good='No. of Data Rows : 30001\nTotal elapsed time (seconds) = 1.25\n'
            (p/'ngspice.log').write_text(good);self.assertTrue(terminal_metadata(p)['numerically_complete'])
            for bad in [good.replace('30001','30000'),good+'run simulation(s) aborted\n',good.replace('1.25','0')]:
                (p/'ngspice.log').write_text(bad)
                with self.assertRaises(ValueError):terminal_metadata(p)
            (p/'ngspice.log').write_text(good);fixture(p,bad='short')
            with self.assertRaises(ValueError):terminal_metadata(p)
