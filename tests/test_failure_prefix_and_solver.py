# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import observe_failure_prefix as observer
import isolate_sparse_solver as solver
from run_ngspice import read_raw


class AbortedPrefixObservation(unittest.TestCase):
    def raw(self,values):
        return b'Title: failed diagnostic\nFlags: real\nNo. Variables: 2\nNo. Points: 0\nVariables:\n0 time time\n1 v(q) voltage\nBinary:\n'+np.asarray(values,dtype='<f8').tobytes()

    def test_available_frames_are_diagnostic_and_cannot_pass_normal_reader(self):
        data=self.raw([[0,0],[1e-9,.1],[2e-9,.2]])+b'partial'
        names,w,m=observer.prefix(data)
        self.assertEqual(names,['time','v(q)']);self.assertEqual(w.shape,(3,2))
        self.assertEqual(m['declared_points'],0);self.assertEqual(m['trailing_bytes'],7)
        self.assertIs(m['completed_waveform'],False)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'failed.raw';p.write_bytes(data)
            with self.assertRaises(ValueError):read_raw(p)

    def test_nonfinite_nonmonotonic_or_missing_start_cannot_be_observed(self):
        for values in [[[0,0],[1e-9,np.nan]],[[0,0],[0,1]],[[1e-9,0],[2e-9,1]]]:
            with self.assertRaises(ValueError):observer.prefix(self.raw(values))


class BoundedSparseSolver(unittest.TestCase):
    def test_only_solver_selection_and_include_path_change(self):
        old=Path('/old');new=Path('/new')
        deck='Native coupled\n.include "/old/library.spice"\n.options reltol=1e-4 abstol=1e-12 method=gear\nVDD VDD 0 1.8\n.tran 1p 12n 0 1p\n.print tran V(Q)\n.end\n'
        result=solver.fixture(deck,old,new)
        self.assertEqual(result.replace('.options sparse\n','').replace('/new/library.spice','/old/library.spice'),deck)
        for bad in [deck.replace('0 1p','0 20p'),deck.replace('.options reltol','.options itl4=100 reltol'),deck+'.options klu\n']:
            with self.assertRaises(ValueError):solver.fixture(bad,old,new)

    def test_unrelated_contexts_cannot_start_a_solver_experiment(self):
        with self.assertRaises(ValueError):solver.prepare(Path('/tmp/retry'))
        with self.assertRaises(ValueError):solver.run(Path('/tmp/retry'))
        with self.assertRaises(ValueError):observer.observe(Path('/tmp/live'))


if __name__=='__main__':unittest.main()
