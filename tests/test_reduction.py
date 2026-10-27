# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reduce_rc import eliminate

class NetworkReduction(unittest.TestCase):
    def test_boundary_admittance_is_preserved(self):
        # Independent dense linear algebra reference for random connected nets.
        rng=np.random.default_rng(130)
        for _ in range(20):
            count=30;boundary=6;graph={str(i):{} for i in range(count)}
            pairs={(i,i+1) for i in range(count-1)}
            pairs|={tuple(sorted(map(int,rng.choice(count,2,replace=False)))) for _ in range(35)}
            for a,b in pairs:
                g=float(rng.uniform(.01,2));graph[str(a)][str(b)]=g;graph[str(b)][str(a)]=g
            def matrix(graph,names):
                k={x:i for i,x in enumerate(names)};m=np.zeros((len(names),len(names)))
                for n,edges in graph.items():
                    for other,g in edges.items():m[k[n],k[n]]+=g;m[k[n],k[other]]-=g
                return m
            def boundary_matrix(m,k):
                return m[:k,:k]-m[:k,k:]@np.linalg.solve(m[k:,k:],m[k:,:k]) if len(m)>k else m
            reference=boundary_matrix(matrix(graph,[str(i) for i in range(count)]),boundary)
            eliminate(graph,{str(i) for i in range(boundary)})
            names=[str(i) for i in range(boundary)]+[str(i) for i in range(boundary,count) if str(i) in graph]
            reduced=boundary_matrix(matrix(graph,names),boundary)
            np.testing.assert_allclose(reduced,reference,rtol=1e-10,atol=1e-10)

if __name__=='__main__':unittest.main()
