# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagnose_distributed_recovery_300_v3 as p


class RegisteredRecoveryTests(unittest.TestCase):
    def test_actual_p40n32_capture_has_complete_typed_recovery_observations(self):
        parent=p.ROOT/'build/diagnostics/p40n32_pre_distributed_pilot_300_v1/3efd00e62550ef86'
        producer=p.family.select_producer(parent)
        self.assertIs(producer,p.family.p40n32)
        identity=json.loads((parent/'manifest.json').read_text())['identity']
        variant=producer.VARIANT
        text=(parent/variant/'bank.spice').read_text()
        top=identity['revisions'][variant]['macro_top']
        nodes=p.switch_nodes(identity['observations'][variant],text,top)
        self.assertEqual(tuple(sum(v['stage']==stage for v in nodes.values())
                               for stage in ('pre','fine')),(6,6))
        self.assertEqual({v['fine_index'] for v in nodes.values()},{0,15,30})
        with self.assertRaisesRegex(ValueError,'signal attachment'):
            p.switch_nodes(identity['observations'][variant],
                           text.replace('Xfine_mim0_c1 pre_out','Xfine_mim0_c1 unknown',1),top)

    def test_pending_case_rejected_before_receipt_creation(self):
        manifest=dict(identity=dict(inputs={},source_identity=dict(pdk_files={},external_files={})),
                      libraries={},tasks=[dict(id='0',variant=p.family.p40n32.VARIANT)])
        with tempfile.TemporaryDirectory(dir=p.ROOT/'build') as folder:
            parent=Path(folder);(parent/'manifest.json').write_text('{}')
            with patch.object(p.family,'select_producer',return_value=p.family.p40n32), \
                 patch.object(p.family.p40n32,'bound',return_value=manifest):
                with self.assertRaisesRegex(ValueError,'Native case is still pending'):
                    p.run(parent,['0'])
