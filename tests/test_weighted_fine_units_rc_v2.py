# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import extract_weighted_fine_units_v2 as extraction


class WeightedFineRCCoverageTests(unittest.TestCase):
    def setUp(self):
        self.report = dict(passed=True, rows=[dict(
            macro=extraction.clock_cells.unit.name(bit), bit=bit, passed=True,
            drc_count='0', lvs_passed=True,
            ports={p: {} for p in extraction.clock_cells.unit.PORTS}) for bit in range(5)])
        self.state = dict(status='physical_complete', passed=True)

    def test_complete_five_cell_family_is_required(self):
        extraction.validate_physical(self.report, self.state)
        for rows in (self.report['rows'][:4], [],
                     self.report['rows'][:4] + [self.report['rows'][0]],
                     self.report['rows'][::-1]):
            with self.assertRaises(ValueError):
                extraction.validate_physical(dict(self.report, rows=rows), self.state)

    def test_dirty_or_misidentified_cell_cannot_be_admitted(self):
        for change in (dict(bit=0), dict(drc_count='2'), dict(lvs_passed=False),
                       dict(passed=False), dict(ports={'NODE': {}})):
            report = deepcopy(self.report)
            report['rows'][4].update(change)
            with self.assertRaises(ValueError):
                extraction.validate_physical(report, self.state)

    def test_incomplete_or_failed_physical_run_is_rejected(self):
        for state in (dict(status='routing', passed=True),
                      dict(status='physical_exception', passed=False),
                      dict(status='physical_complete', passed=False)):
            with self.assertRaises(ValueError):
                extraction.validate_physical(self.report, state)


if __name__ == '__main__':
    unittest.main()
