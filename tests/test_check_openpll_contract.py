# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import check_openpll_contract as check


class CurrentOpenPllContract(unittest.TestCase):
    req=dict(clock_test_mhz=[390,400,410],clock_duty=[.45,.5,.55])
    def edges(self,mhz,duty=.5):
        period=1000/mhz
        return np.array([(i*period+phase,value) for i in range(12) for phase,value in [(0,1),(duty*period,0)]])

    def test_previous_wider_contract_cannot_admit_385_or_415_mhz(self):
        for mhz in [385,415]:
            edges=self.edges(mhz)
            self.assertTrue(check.original.stats(edges[:,0],edges[:,1])['passed'])
            self.assertFalse(check.metrics(edges,self.req)['passed'])

    def test_current_frequency_and_duty_boundaries_are_admitted(self):
        for mhz in [390,400,410]:
            for duty in [.45,.5,.55]:self.assertTrue(check.metrics(self.edges(mhz,duty),self.req)['passed'])

    def test_invalid_edges_cannot_be_silently_ignored(self):
        for kind in ['nan','duplicate_time','backward_time','unknown_level','repeated_level']:
            edges=self.edges(400)
            if kind=='nan':edges[3,0]=np.nan
            elif kind=='duplicate_time':edges[3,0]=edges[2,0]
            elif kind=='backward_time':edges[3,0]=edges[2,0]-.1
            elif kind=='unknown_level':edges[3,1]=2
            else:edges[3,1]=edges[2,1]
            with self.assertRaises(ValueError):check.metrics(edges,self.req)

    def test_out_of_range_duty_is_rejected(self):
        for duty in [.44,.56]:self.assertFalse(check.metrics(self.edges(400,duty),self.req)['passed'])
