# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_dll_reverse_conditioning as reverse


class ReversedDLLConditioning(unittest.TestCase):
    def manifest(self):
        return dict(identity=dict(conditioning_profile='reverse_slew_200_20',
            code={Path(reverse.__file__).name:'sha'}), tasks=[dict(id=n, spec=dict(kind='phase',
                process='ss', temperature=40, mhz=400, reference_slew_ps=200,
                feedback_slew_ps=20)) for n in reverse.CASES])

    def test_reversed_profile_restores_original_runner_after_success_and_failure(self):
        previous = reverse.original.CASES, reverse.original.bound
        with reverse.profile():
            self.assertEqual(reverse.original.CASES, reverse.CASES)
            self.assertIs(reverse.original.bound, reverse.bound)
        self.assertEqual((reverse.original.CASES, reverse.original.bound), previous)
        with self.assertRaisesRegex(ValueError, 'test failure'):
            with reverse.profile(): raise ValueError('test failure')
        self.assertEqual((reverse.original.CASES, reverse.original.bound), previous)

    def test_declared_slew_cannot_differ_from_reversed_profile(self):
        m = self.manifest()
        with patch.object(reverse, 'ORIGINAL_BOUND', return_value=m):
            self.assertEqual(reverse.bound(Path('/unused')), m)
        for key, value in [('reference_slew_ps', 20), ('feedback_slew_ps', 200),
                           ('process', 'tt'), ('temperature', 25), ('mhz', 410)]:
            bad = deepcopy(m); bad['tasks'][0]['spec'][key] = value
            with patch.object(reverse, 'ORIGINAL_BOUND', return_value=bad):
                with self.assertRaisesRegex(ValueError, 'profile changed'):
                    reverse.bound(Path('/unused'))

    def test_runner_and_independent_verifier_use_the_same_reversed_case_set(self):
        def check(out):
            self.assertEqual(reverse.original.CASES, reverse.CASES)
            self.assertEqual([int(n.split('_')[3].removesuffix('ps')) for n in reverse.CASES], [-50, 150, -150])
            return {'qualified_phy': False}
        with patch.object(reverse.original, 'run', side_effect=check), \
                patch.object(reverse.original, 'verify', side_effect=check):
            with reverse.profile():
                self.assertFalse(reverse.original.run(Path('/unused'))['qualified_phy'])
            self.assertFalse(reverse.verify(Path('/unused'))['qualified_phy'])

    def test_failed_forward_experiment_blocks_reverse_dispatch(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'forward';parent.mkdir();(parent/'summary.json').write_text('{}')
            with patch.object(reverse,'ROOT',root),patch.object(reverse,'bound',return_value={'identity':{'parent':'forward'}}), \
                    patch.object(reverse.original,'verify',return_value={'input_conditioning_diagnostic_passed':False}), \
                    patch.object(reverse.original,'run') as run:
                with self.assertRaisesRegex(ValueError,'reverse dispatch held'):reverse.run(root/'new')
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
