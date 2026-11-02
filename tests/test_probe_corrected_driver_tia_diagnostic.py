# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_corrected_driver_tia_diagnostic as link


class CorrectedCoupledNativeLink(unittest.TestCase):
    def fixture(self):
        old=Path('/work/OpenLVDS/build/diagnostics/analog_link_pilot/old')
        new=Path('/work/OpenLVDS/build/diagnostics/receiver_feedback_link_diagnostic/new')
        probes=['V(X'+instance+':'+link.TOP+'__'+leaf+')' for instance in ['DR','CR'] for leaf in link.LEAVES]
        deck=('Coupled link\n.include "'+str(old)+'/library.spice"\nVCLK CLK 0 PWL(0 0 1n 1.8)\n'
            '.tran 20p 188.049n 0 20p\n.print tran V(RP) '+' '.join(probes)+'\n.end\n')
        nodes={leaf:'XRC:'+link.TOP+'__'+leaf+'.t1' for leaf in link.LEAVES}
        return old,new,deck,nodes

    def test_only_library_probes_and_declared_maximum_step_change(self):
        old,new,deck,nodes=self.fixture();changed=link.fixture(deck,old,new,nodes)
        restored=changed.replace(str(new),str(old))
        for instance in ['DR','CR']:
            for leaf in link.LEAVES:
                restored=restored.replace('V(X'+instance+':'+link.TOP+'__'+leaf+'.t1)',
                    'V(X'+instance+':'+link.TOP+'__'+leaf+')')
        restored=restored.replace('.tran 20p 188.049n 0 1p','.tran 20p 188.049n 0 20p')
        self.assertEqual(restored,deck)
        self.assertIn('.tran 20p 188.049n 0 1p',changed)

    def test_shortened_coarse_and_ambiguous_fixtures_are_refused(self):
        old,new,deck,nodes=self.fixture()
        for bad in [deck.replace('188.049n','100n'),deck.replace('0 20p','0 100p'),
                    deck.replace('V(RP)','V(RP) V(XDR:'+link.TOP+'__PP)')]:
            with self.assertRaises(ValueError):
                link.fixture(bad,old,new,nodes)

    def test_incomplete_native_controls_cannot_start_driver_or_link_job(self):
        with patch.object(link,'completed_replay',side_effect=ValueError('native incomplete')),patch.object(link.driver,'run') as run:
            with self.assertRaisesRegex(ValueError,'native incomplete'):
                link.prepare(Path('parent'),Path('replay'),Path('driver'))
            run.assert_not_called()

    def test_partial_coupled_trace_is_preserved_before_any_recheck_or_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'build/diagnostics/receiver_feedback_link_diagnostic/partial';out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(simulator_provenance='test',inputs={},code={},diagnostic_only=True,maximum_step_ps=1),files={})))
            raw=out/'bench.raw';raw.write_bytes(b'original incomplete coupled trace')
            with patch.object(link,'ROOT',root),patch.object(link,'provenance',return_value='test'),patch.object(link,'completed_replay') as check,patch.object(link.subprocess,'run') as launch:
                with self.assertRaisesRegex(ValueError,'Partial corrected native link retained'):
                    link.run(out)
                check.assert_not_called();launch.assert_not_called()
            self.assertEqual(raw.read_bytes(),b'original incomplete coupled trace')



class CompletedFailedReplay(unittest.TestCase):
    def test_completed_false_verdict_is_retained_without_component_admission(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(link,'ROOT',Path(tmp)),patch.object(link.native_probe,'run') as remeasure,patch.object(link.receiver,'recheck') as admission:
            q=Path(tmp)/'build/diagnostics/receiver_replay/complete';q.mkdir(parents=True)
            (q/'manifest.json').write_text(json.dumps(dict(identity=dict(tia_restore_variant='tia_r4'))))
            for name in ['captured','sharp_control']:
                p=q/name;p.mkdir();(p/'summary.json').write_text('{}')
            report=dict(diagnostic_complete=True,native_clock_passed=False,qualified_phy=False,manifest_sha256=link.sha(q/'manifest.json'))
            (q/'summary.json').write_text(json.dumps(report));before=(q/'summary.json').read_bytes()
            result=link.completed_replay(q)
            self.assertFalse(result['legacy_native_clock_passed']);self.assertEqual((q/'summary.json').read_bytes(),before)
            remeasure.assert_called_once_with(q);admission.assert_not_called()

    def test_partial_or_other_family_cannot_launch_native_remeasurement(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(link,'ROOT',Path(tmp)),patch.object(link.native_probe,'run') as remeasure:
            q=Path(tmp)/'build/diagnostics/receiver_replay/partial';q.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError,'Complete both'):link.completed_replay(q)
            remeasure.assert_not_called()
            (q/'manifest.json').write_text(json.dumps(dict(identity=dict(tia_fast_frontend_variant='fast_tia_r4'))))
            (q/'summary.json').write_text('{}')
            for name in ['captured','sharp_control']:
                p=q/name;p.mkdir();(p/'summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'original feedback-receiver family'):link.completed_replay(q)
            remeasure.assert_not_called()


if __name__=='__main__':unittest.main()
