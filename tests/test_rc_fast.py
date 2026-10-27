# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rc_fast import reduce_quick

class QuickNodes(unittest.TestCase):
    def test_complex_boundary_admittance(self):
        rng=np.random.default_rng(130)
        for _ in range(8):
            n=20;k=5;g={str(i):{} for i in range(n)};c={str(i):{} for i in range(n)}
            for i in range(1,n):
                for j in rng.choice(i,min(i,2),replace=False):
                    j=int(j);v=float(rng.uniform(.5,2));g[str(i)][str(j)]=v;g[str(j)][str(i)]=v
                v=float(rng.uniform(1e-18,1e-17));c[str(i)]['0']=v;c['0'][str(i)]=v
            def matrix(g,c,names,f):
                at={x:i for i,x in enumerate(names)};y=np.zeros((len(names),len(names)),complex)
                for graph,scale in [(g,1),(c,2j*np.pi*f)]:
                    for a,edges in graph.items():
                        for b,value in edges.items():
                            y[at[a],at[a]]+=scale*value;y[at[a],at[b]]-=scale*value
                return y
            def boundary(y):return y[:k,:k]-y[:k,k:]@np.linalg.solve(y[k:,k:],y[k:,:k]) if len(y)>k else y
            names=[str(i) for i in range(n)]
            reference={f:boundary(matrix(g,c,names,f)) for f in [0,1e9,1e10]}
            removed,_=reduce_quick(g,c,{str(i) for i in range(k)})
            self.assertGreater(removed,0)
            names=[str(i) for i in range(k)]+[str(i) for i in range(k,n) if str(i) in g]
            for f,expected in reference.items():
                actual=boundary(matrix(g,c,names,f))
                np.testing.assert_allclose(actual,expected,rtol=1e-3,atol=1e-8)

if __name__=='__main__':unittest.main()
