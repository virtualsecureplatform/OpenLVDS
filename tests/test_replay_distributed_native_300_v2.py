# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import replay_distributed_native_300_v2 as p


class ReplayRefusalTests(unittest.TestCase):
    def manifest(self):
        return dict(identity=dict(inputs={}, source_identity=dict(pdk_files={}, external_files={})),
                    libraries={}, tasks=[dict(id='0', variant=p.p40n32.VARIANT)])

    def test_unknown_duplicate_and_empty_selection_rejected(self):
        with patch.object(p, 'select_producer', return_value=p.p40n32), \
                 patch.object(p.p40n32, 'bound', return_value=self.manifest()):
            for selection in ([], ['0', '0'], ['99']):
                with self.assertRaises(ValueError):
                    p.run(p.ROOT / 'build/unused-medium-pre-replay', selection)

    def test_incomplete_case_rejected_before_receipt_creation(self):
        with tempfile.TemporaryDirectory(dir=p.ROOT / 'build') as folder:
            parent = Path(folder)
            (parent / 'manifest.json').write_text('{}')
            with patch.object(p, 'select_producer', return_value=p.p40n32), \
                 patch.object(p.p40n32, 'bound', return_value=self.manifest()):
                with self.assertRaisesRegex(ValueError, 'Native case is still pending'):
                    p.run(parent, ['0'])

    def test_execution_failure_or_mismatched_task_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory(dir=p.ROOT / 'build') as folder:
            parent = Path(folder)
            (parent / 'manifest.json').write_text('{}')
            (parent / '0').mkdir()
            for row in (dict(error='native failure', result={}, task=self.manifest()['tasks'][0], files={}),
                        dict(error=None, task=dict(id='1'), files={'bench.raw': 'x', 'bench.cir': 'x'})):
                (parent / '0/summary.json').write_text(json.dumps(row))
                with patch.object(p, 'select_producer', return_value=p.p40n32), \
                 patch.object(p.p40n32, 'bound', return_value=self.manifest()):
                    with self.assertRaisesRegex(ValueError, 'Require complete error-free'):
                        p.run(parent, ['0'])

    def test_only_registered_native_producers_are_selected(self):
        for folder, expected in ((p.p40n32.PREVIOUS, p.medium),
                                 (p.medium.PREVIOUS, p.distributed)):
            self.assertIs(p.select_producer(folder), expected)
        with tempfile.TemporaryDirectory(dir=p.ROOT / 'build') as folder:
            parent=Path(folder)
            (parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=p.p40n32.VERSION))))
            self.assertIs(p.select_producer(parent), p.p40n32)
            (parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version='unsupported'))))
            with self.assertRaisesRegex(ValueError,'Unsupported captured bank producer'):
                p.select_producer(parent)
