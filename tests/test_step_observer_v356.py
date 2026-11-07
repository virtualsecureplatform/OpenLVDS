# SPDX-License-Identifier: GPL-3.0-only
"""Prove diagnostic source additions leave the original numerical code intact."""
from pathlib import Path
import re
import sys
import tarfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import setup_step_observer_v356 as p


class StepObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=p.ROOT/'build/tools/ngspice-42-option-audit/ngspice_42+ds.orig.tar.gz'
        if p.sha(path)!=p.ARCHIVES[path.name]:raise ValueError('Pinned original source changed')
        cls.files={}
        with tarfile.open(path) as tar:
            for member in tar.getmembers():
                name='/'.join(Path(member.name).parts[1:])
                if member.isfile() and (name in ('src/maths/ni/niiter.c','src/spicelib/analysis/dctran.c',
                    'src/spicelib/analysis/ckttrunc.c') or re.search(r'/devices/(bsim4(?:v\d+)?|cap)/[^/]*trunc.c$',name)):
                    cls.files[name]=tar.extractfile(member).read().decode()

    def test_every_required_original_numerical_source_is_exactly_recovered(self):
        self.assertEqual(len(self.files),8)
        for name,original in self.files.items():
            changed,sites=p.instrument(name,original)
            self.assertGreater(sites,0,name)
            self.assertEqual(p.strip(changed),original,name)
            self.assertIn('ngspice/openlvds_step_trace.h',changed)

    def test_each_original_charge_call_executes_once_with_original_arguments(self):
        for name,original in self.files.items():
            if '/devices/' not in name:continue
            changed,sites=p.instrument(name,original)
            calls=re.findall(r'CKTterr\([^;]+;',original)
            self.assertEqual(len(calls),sites)
            self.assertEqual(re.findall(r'CKTterr\([^;]+;',changed),calls)
            self.assertEqual(changed.count('kind=charge_trunc'),sites)

    def test_original_iteration_limit_and_step_rejection_rules_remain_literal(self):
        original=self.files['src/maths/ni/niiter.c'];changed,_=p.instrument('src/maths/ni/niiter.c',original)
        self.assertIn('if (maxIter < 100)\n        maxIter = 100;',changed)
        self.assertIn('return(E_ITERLIM);',changed)
        original=self.files['src/spicelib/analysis/dctran.c'];changed,_=p.instrument('src/spicelib/analysis/dctran.c',original)
        self.assertIn('ckt->CKTdelta = ckt->CKTdelta/8;',changed)
        self.assertIn('kind=noncon_reject',changed)
        self.assertIn('kind=trunc_decision',changed)

    def test_logging_is_opt_in_bounded_and_unexpected_source_is_rejected(self):
        self.assertIn('getenv("OPENLVDS_STEP_TRACE")',p.HEADER)
        self.assertIn('t > 200e-12',p.HEADER)
        self.assertIn('count >= 50000',p.HEADER)
        self.assertNotIn('ckt->',p.HEADER)
        original=self.files['src/maths/ni/niiter.c']
        with self.assertRaises(ValueError):p.instrument('src/maths/ni/niiter.c',original.replace('iterno > maxIter','iterno >= maxIter'))
        unchanged,sites=p.instrument('unrelated.c','double x=1e-12;\n')
        self.assertEqual(unchanged,'double x=1e-12;\n');self.assertEqual(sites,0)


if __name__=='__main__':unittest.main()
