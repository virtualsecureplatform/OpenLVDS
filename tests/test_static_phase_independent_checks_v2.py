# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import check_static_phase_klayout_v2 as klayout
import check_static_phase_antenna_v2 as antenna


class IndependentCounterChecks(unittest.TestCase):
    def test_drc_requires_complete_report_correct_top_and_counts_every_item(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'report.xml'
            item='<item><category>metal</category><cell>counter</cell><values/></item>'
            p.write_text('<report-database><top-cell>counter</top-cell><items>'+item*2+'</items></report-database>')
            result=klayout.parse_report(p,'counter');self.assertEqual(result['violation_count'],2)
            self.assertEqual(result['violations_by_category'],{'metal':2})
            with self.assertRaises(ValueError):klayout.parse_report(p,'other')
            p.write_text('<report-database><top-cell>counter</top-cell></report-database>')
            with self.assertRaises(ValueError):klayout.parse_report(p,'counter')

    def test_antenna_requires_successful_command_and_every_native_mos(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'result.txt';ext=root/'flat.ext'
            p.write_text('0\n0\nCOMPLETE\n');ext.write_text('tech sky130A\n'+'device msubckt sky130_fd_pr__nfet_01v8 0 0\n'*402)
            self.assertTrue(antenna.parse_result(p,ext)['installed_partial_antenna_passed'])
            p.write_text('0\n3\nCOMPLETE\n');self.assertFalse(antenna.parse_result(p,ext)['installed_partial_antenna_passed'])
            p.write_text('1\n0\nCOMPLETE\n')
            with self.assertRaises(ValueError):antenna.parse_result(p,ext)
            p.write_text('0\n0\nCOMPLETE\n');ext.write_text('tech sky130A\n')
            with self.assertRaises(ValueError):antenna.parse_result(p,ext)


if __name__=='__main__':unittest.main()
