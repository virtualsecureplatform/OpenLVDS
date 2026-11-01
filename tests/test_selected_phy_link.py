# SPDX-License-Identifier: GPL-3.0-only
import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import selected_phy_phase as phase
import simulate_selected_link as link

class SelectedLink(unittest.TestCase):
    def test_measured_phase_moves_only_quarter_clock_and_budgets_full_range(self):
        args=SimpleNamespace(mhz=400,duty=.5,clock_source='ideal',jitter_pp_ps=100,dll_phase=True,bundle='chosen',process='tt',temperature=25)
        plain=SimpleNamespace(**dict(vars(args),dll_phase=False))
        c0,c90,rises,period,_=link.original.clocks(plain,800)
        evidence=dict(quarter_phase_min_ps=500,quarter_phase_max_ps=600,evidence_sha256='bound')
        with patch.object(link,'phase',return_value=evidence):actual=link.clocks(args,800)
        self.assertEqual(actual[0],c0);self.assertTrue((actual[2]==rises).all());self.assertEqual(actual[3],period)
        self.assertEqual(actual[1][0],c90[0])
        for (at,value),(old,oldvalue) in zip(actual[1][1:],c90[1:]):
            self.assertAlmostEqual(at-old,-.075);self.assertEqual(value,oldvalue)
        result=link.budget(dict(setup_margin_ps=310,hold_margin_ps=280),args.phase_evidence)
        self.assertEqual(result['setup_margin_ps'],210);self.assertEqual(result['hold_margin_ps'],180)
        self.assertEqual(result['raw_hold_margin_ps'],280)

    def test_partial_and_changed_cached_waveforms_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bench.raw').write_bytes(b'partial')
            with self.assertRaisesRegex(ValueError,'Incomplete selected link'):link.existing(root)
            self.assertEqual((root/'bench.raw').read_bytes(),b'partial')
            (root/'bench.cir.prn').write_text('wave')
            report=dict(waveform_sha256=link.selected_phy.digest(root/'bench.cir.prn'));(root/'summary.json').write_text(json.dumps(report))
            self.assertEqual(link.existing(root),report)
            (root/'bench.cir.prn').write_text('changed')
            with self.assertRaisesRegex(ValueError,'waveform changed'):link.existing(root)

    def test_captured_files_cannot_be_silently_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'library.spice';link.store(p,b'original');link.store(p,b'original')
            with self.assertRaisesRegex(ValueError,'Captured selected-link file changed'):link.store(p,b'new')
            self.assertEqual(p.read_bytes(),b'original')

    def phase_fixture(self,root):
        qualification=root/'build/diagnostics/dll_qualification/current';qualification.mkdir(parents=True)
        text='.subckt openlvds_dll A B\nR0 A B 1\n.ends openlvds_dll\n.subckt lvds_bias A B\nR0 A B 2\n.ends lvds_bias\n'
        (qualification/'full.spice').write_text(text);folder=qualification/'native';folder.mkdir()
        (folder/'bench.cir').write_text('pinned fixture');(folder/'bench.cir.prn').write_text('pinned waveform')
        task=dict(id='native',fast_rc=False,spec=dict(kind='loop',process='tt',temperature=25,mhz=400,duty=.5),deck_sha256=phase.selected_phy.digest(folder/'bench.cir'))
        (qualification/'manifest.json').write_text(json.dumps(dict(tasks=[task])))
        metrics=dict(passed=True,quarter_phase_min_ps=620,quarter_phase_max_ps=630)
        report=dict(passed=True,deck_sha256=task['deck_sha256'],waveform_sha256=phase.selected_phy.digest(folder/'bench.cir.prn'),metrics=metrics)
        (folder/'summary.json').write_text(json.dumps(report))
        bundle=root/'build/diagnostics/selected_phy/chosen';bundle.mkdir(parents=True)
        (bundle/'manifest.json').write_text(json.dumps(dict(identity=dict(paths=dict(qualification=str(qualification.relative_to(root)))))))
        return bundle,text,metrics,folder

    def test_phase_requires_the_same_bias_and_dll_and_exact_complete_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle,text,metrics,folder=self.phase_fixture(root)
            with patch.object(phase,'ROOT',root),patch.object(phase.selected_phy,'load',return_value=(text.encode(),{},{})),patch.object(phase,'evaluate',return_value=metrics):
                result=phase.phase(bundle,'tt',25,400,.5);self.assertEqual(result['quarter_phase_min_ps'],620)
                with self.assertRaisesRegex(ValueError,'Missing or ambiguous'):phase.phase(bundle,'ss',25,400,.5)
                (folder/'bench.cir.prn').write_text('changed')
                with self.assertRaisesRegex(ValueError,'evidence changed'):phase.phase(bundle,'tt',25,400,.5)
            with patch.object(phase,'ROOT',root),patch.object(phase.selected_phy,'load',return_value=(text.replace('R0 A B 2','R0 A B 3').encode(),{},{})):
                with self.assertRaisesRegex(ValueError,'phase circuit changed: lvds_bias'):phase.phase(bundle,'tt',25,400,.5)

if __name__=='__main__':unittest.main()
