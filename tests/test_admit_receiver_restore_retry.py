# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import admit_receiver_restore_retry as admission


class RestorationRetryAdmission(unittest.TestCase):
    def fixture(self, root):
        old = root/'build/diagnostics/receiver_restore_threshold/original'
        new = root/'build/diagnostics/receiver_restore_threshold/retry'
        tasks = [dict(id=v) for v in admission.matrix.pilot.VARIANTS]
        old.mkdir(parents=True); new.mkdir(parents=True)
        (old/'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
        identity = dict(numerical_retry_parent=str(old.relative_to(root)), maximum_step_ps=1,
            original_maximum_step_ps=50, code={admission.retry.NAME: admission.sha(Path(admission.retry.__file__))})
        (new/'manifest.json').write_text(json.dumps(dict(tasks=tasks, identity=identity)))
        for task in tasks:
            a,b = old/task['id'], new/task['id']; a.mkdir(); b.mkdir()
            for name in ['source.spice', 'candidate.spice']:
                (a/name).write_text('unchanged circuit bytes\n'); (b/name).write_bytes((a/name).read_bytes())
            deck = f'.include "{a}/source.spice"\n.options method=gear reltol=1e-4\n.tran 10p 144n 0 50p\n'
            (a/'bench.cir').write_text(deck)
            (b/'bench.cir').write_text(admission.retry.tighten(deck).replace(str(a),str(b)))
        return old,new

    def test_accepts_only_declared_matched_numerical_edit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(admission, 'ROOT', Path(tmp)):
            old,new = self.fixture(Path(tmp)); admission.replacement(old,new)
            p = new/'restore_lvt_n8/bench.cir'; p.write_text(p.read_text().replace('reltol=1e-4', 'reltol=1e-3'))
            with self.assertRaisesRegex(ValueError, 'more than maximum step'):
                admission.replacement(old,new)

    def test_changed_circuit_cannot_be_labelled_numerical_retry(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(admission, 'ROOT', Path(tmp)):
            old,new = self.fixture(Path(tmp))
            (new/'restore_lvt_n4/source.spice').write_text('changed transistor\n')
            with self.assertRaisesRegex(ValueError, 'changed a circuit'):
                admission.replacement(old,new)

    def test_retry_for_another_parent_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(admission, 'ROOT', Path(tmp)):
            old,new = self.fixture(Path(tmp)); p = new/'manifest.json'; m = json.loads(p.read_text())
            m['identity']['numerical_retry_parent'] = 'unrelated'; p.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, 'exact declared matched'):
                admission.replacement(old,new)

    def test_partial_matrix_cannot_dispatch_a_missing_simulation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(admission, 'ROOT', Path(tmp)):
            identity = dict(code={admission.NAME: admission.sha(Path(admission.__file__))}, children=[dict(root='missing')])
            name = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            root = Path(tmp)/'build/diagnostics/receiver_restore_threshold_matrix'/name; root.mkdir(parents=True)
            (root/'manifest.json').write_text(json.dumps(dict(identity=identity)))
            with patch.object(admission.matrix, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'cannot dispatch missing work'):
                    admission.run(root)
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
