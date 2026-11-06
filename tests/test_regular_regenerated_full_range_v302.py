# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_regular_regenerated_full_range_v302 as p


class FullRangeFollowupTests(unittest.TestCase):
    def states(self):
        periodic='build/diagnostics/regular_regenerated_joint_periodic_v288/0123456789abcdef'
        return dict(sparse=dict(status='sparse_clock_pvt_complete',artifacts=dict(periodic=periodic,
            pvt='build/diagnostics/regular_regenerated_pvt_v291/0123456789abcdef')),
            dense=dict(status='dense_curve_complete',artifacts=dict(periodic=periodic,
            dense='build/diagnostics/regular_regenerated_dense_v294/0123456789abcdef')))

    def test_both_complete_matching_lineages_require_independent_donor_checks(self):
        states=self.states()
        with patch.object(p.sparse,'require_matrix') as sparse,patch.object(p.dense,'require_curve') as dense:
            paths=p.ready_donors(states)
            self.assertEqual(paths,[p.ROOT/states[n]['artifacts'][f] for n,f in (('sparse','pvt'),('dense','dense'))])
            sparse.assert_called_once_with(paths[0]);dense.assert_called_once_with(paths[1])
        with patch.object(p.sparse,'require_matrix',side_effect=ValueError('Native matrix failed')):
            with self.assertRaisesRegex(ValueError,'Native matrix failed'):p.ready_donors(states)

    def test_running_failed_missing_or_foreign_donor_never_advances(self):
        for name,_,field,_ in p.DONORS:
            for status in ('waiting_for_native_transport','failed','running_dense'):
                states=self.states();states[name]['status']=status
                with self.assertRaisesRegex(ValueError,'must complete'):p.ready_donors(states)
            states=self.states();states[name]['artifacts'].pop(field)
            with self.assertRaises(ValueError):p.ready_donors(states)
            states=self.states();states[name]['artifacts'][field]='build/diagnostics/unrelated/0123456789abcdef'
            with self.assertRaises(ValueError):p.ready_donors(states)

    def test_two_passing_but_different_periodic_ancestors_are_rejected_before_consuming(self):
        states=self.states();states['dense']['artifacts']['periodic']='build/diagnostics/regular_regenerated_joint_periodic_v288/fedcba9876543210'
        with patch.object(p.sparse,'require_matrix') as check:
            with self.assertRaisesRegex(ValueError,'lineages differ'):p.ready_donors(states)
            check.assert_not_called()
        states=self.states();states['dense']['artifacts']['periodic']=''
        with self.assertRaisesRegex(ValueError,'periodic donor'):p.ready_donors(states)

    def test_conflicting_source_hashes_cannot_be_overwritten_when_merging_guards(self):
        a={'scripts/a.py':'a','scripts/b.py':'b'};b={'scripts/a.py':'a','scripts/c.py':'c'}
        original=deepcopy((a,b))
        self.assertEqual(p.merge_inputs([a,b]),dict(a,**b));self.assertEqual((a,b),original)
        b['scripts/a.py']='changed'
        with self.assertRaisesRegex(ValueError,'hashes disagree'):p.merge_inputs([a,b])


if __name__=='__main__':unittest.main()
