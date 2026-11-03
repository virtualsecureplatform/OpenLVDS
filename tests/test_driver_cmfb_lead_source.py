# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import qualify_driver_cmfb_lead_source as source


class ActualLeadSourceQualification(unittest.TestCase):
    def test_pilot_uses_actual_schematic_and_preserves_both_evidence_chains(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            folder = parent / 'tt_25_negative_op'
            folder.mkdir()
            (folder / 'source.spice').write_text('original schematic')
            diagnostic = {'identity': {'stage': 'pilot', 'inputs': {'common': 'same',
                'diagnostic': 'd'}, 'code': {'lead': 'code'}}}
            original = {'identity': {'stage': 'full', 'inputs': {'common': 'same',
                'original': 's'}, 'code': {'original': 'code'}}}
            with patch.object(source.campaign, 'verified', side_effect=[
                    (diagnostic, {'diagnostic-proof': 'proof', 'common': 'same'}),
                    (original, {'source-proof': 'proof', 'common': 'same'})]), \
                    patch.object(source, 'design_model', return_value='actual schematic') as design, \
                    patch.object(source, 'write', return_value=parent / 'prepared') as write:
                self.assertEqual(source.prepare_pilot(Path('/diagnostic'), parent), parent / 'prepared')
                design.assert_called_once_with(diagnostic, 'original schematic')
                args = write.call_args.args
                self.assertEqual(args[3:], ('actual schematic', 'pilot'))
                self.assertEqual(set(args[1]), {'common', 'diagnostic', 'original',
                    'diagnostic-proof', 'source-proof'})

    def test_failed_diagnostic_cannot_prepare_actual_source(self):
        with patch.object(source.campaign, 'verified', side_effect=ValueError('failed diagnostic')), \
                patch.object(source, 'write') as write:
            with self.assertRaisesRegex(ValueError, 'failed diagnostic'):
                source.prepare_pilot(Path('/diagnostic'), Path('/original'))
            write.assert_not_called()

    def test_full_campaign_cannot_substitute_for_six_case_source_pilot(self):
        with patch.object(source.campaign, 'verified', return_value=(
                {'identity': {'stage': 'full'}}, {})), patch.object(source, 'write') as write:
            with self.assertRaisesRegex(ValueError, 'pilot campaign'):
                source.prepare_full(Path('/full'))
            write.assert_not_called()

    def test_actual_proposal_requires_both_hash_and_exact_transformation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = root / 'proposal.spice'
            proposal.write_text('actual schematic')
            manifest = {'identity': {'design_proposal': 'proposal.spice',
                'inputs': {'proposal.spice': source.sha(proposal)}}}
            with patch.object(source, 'ROOT', root), patch.object(source.lead, 'transform',
                    return_value='different schematic'):
                with self.assertRaisesRegex(ValueError, 'single calculated proposal'):
                    source.design_model(manifest, 'original')
            proposal.write_text('modified')
            with patch.object(source, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'not bound'):
                    source.design_model(manifest, 'original')

    def test_full_preparation_preserves_fixture_and_covers_all_fifteen_points(self):
        repository = source.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            shutil.copyfile(repository / 'requirements.json', root / 'requirements.json')
            for name in ['qualify_driver_cmfb_lead_source.py', 'driver_source_campaign.py',
                         'driver_geometric_shape.py', 'probe_driver_cmfb_lead.py']:
                shutil.copyfile(repository / 'scripts' / name, root / 'scripts' / name)
            parent = root / 'pilot'
            for op in ['negative_op', 'positive_op']:
                folder = parent / ('tt_25_' + op)
                folder.mkdir(parents=True)
                (folder / 'bench.cir').write_text(f'''Source fixture
.lib "/pdk/sky130.lib.spice" tt
.include "{folder}/source.spice"
.options device temp=25
VIO VDDIO 0 3.3
VDIG VDDD 0 1.8
VREF VREF 0 1.2
IREF IREF 0 35u
RT P N 100
CP P 0 2p
CN N 0 2p
.tran 1p 80n 0 1p
.print tran V(P) V(N)
.end
''')
            model = '.subckt unused P N\nR0 P N 100\n.ends unused\n'
            with patch.object(source, 'ROOT', root), patch.object(source.campaign, 'ROOT', root), \
                    patch.object(source.campaign, 'provenance', return_value={'test': 'runtime'}):
                out = source.write(parent, {}, {}, model, 'full')
                manifest = source.campaign.context(out, source)
                self.assertEqual(len(manifest['tasks']), 30)
                self.assertEqual(len(manifest['identity']['points']), 15)
                self.assertFalse(manifest['qualified_phy'])
                for task in manifest['tasks']:
                    folder = out / task['id']
                    deck = (folder / 'bench.cir').read_text()
                    self.assertIn('.tran 1p 80n 0 1p', deck)
                    self.assertIn('.options device temp=' + str(task['temperature']), deck)
                    self.assertIn('VIO VDDIO 0 3.3', deck)
                    self.assertEqual((folder / 'source.spice').read_text(), model)
                (out / manifest['tasks'][0]['id'] / 'source.spice').write_text('changed')
                with self.assertRaisesRegex(ValueError, 'evidence changed'):
                    source.campaign.context(out, source)
