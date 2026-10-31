# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reduce_rc import eliminate


class DenseExactElimination(unittest.TestCase):
    def test_higher_degree_elimination_preserves_complex_terminal_admittance(self):
        rng=np.random.default_rng(230)
        count=40;boundary=8
        graph={str(i):{} for i in range(count)}
        pairs={(i,i+1) for i in range(count-1)}
        pairs|={tuple(sorted(map(int,rng.choice(count,2,replace=False)))) for _ in range(100)}
        for a,b in pairs:
            g=float(10**rng.uniform(-2,2));graph[str(a)][str(b)]=g;graph[str(b)][str(a)]=g
        caps=10**rng.uniform(-13,-10,boundary)
        def terminals(network,hz):
            names=[str(i) for i in range(boundary)]+sorted(n for n in network if int(n)>=boundary)
            index={name:i for i,name in enumerate(names)}
            y=np.zeros((len(names),len(names)),complex)
            for a,neighbors in network.items():
                for b,g in neighbors.items():y[index[a],index[a]]+=g;y[index[a],index[b]]-=g
            y[np.arange(boundary),np.arange(boundary)]+=2j*np.pi*hz*caps
            return y[:boundary,:boundary]-y[:boundary,boundary:]@np.linalg.solve(y[boundary:,boundary:],y[boundary:,:boundary]) if len(y)>boundary else y
        for degree in [6,8,12]:
            reduced=deepcopy(graph)
            self.assertGreater(eliminate(reduced,{str(i) for i in range(boundary)},degree),0)
            for hz in [1e4,1e7,1e10]:
                np.testing.assert_allclose(terminals(reduced,hz),terminals(graph,hz),rtol=1e-10,atol=1e-10)
