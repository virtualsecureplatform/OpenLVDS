# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_counter_matched_buffers_v306 as p


class CounterMatchedBuffersTests(unittest.TestCase):
    def test_exact_paired_coverage_prioritizes_both_sixty_percent_variants(self):
        specs=p.specifications();self.assertEqual(len(specs),24)
        for a,b in zip(specs[::2],specs[1::2]):
            self.assertEqual(a['buffer_variant'],'baseline');self.assertEqual(b['buffer_variant'],'matched')
            self.assertEqual({k:v for k,v in a.items() if k!='buffer_variant'},{k:v for k,v in b.items() if k!='buffer_variant'})
        self.assertEqual({(s['temperature'],s['duty'],s['stop_level']) for s in specs},
            {(t,d,level) for t in (0,40) for d in (.4,.5,.6) for level in (0,1)})
        self.assertEqual([(s['duty'],s['stop_level']) for s in specs[:2]],[(.6,0),(.6,0)])

    def fixture(self):
        root=p.ROOT
        physical=root/'build/diagnostics/fast_clear_counter_physical_v267/5f2c400d640d10fb'
        bank=root/'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
        counter=root/'build/diagnostics/fast_clear_counter_shared_rc_v269/12b91a2b04a05d8c'
        if not all((q/'manifest.json').exists() for q in (physical,bank,counter)):self.skipTest('Qualified native component fixtures required')
        pi=json.loads((physical/'manifest.json').read_text())['identity'];ci=json.loads((counter/'manifest.json').read_text())['identity']
        pilot=root/ci['source'];storage=root/pi['component'];sr=json.loads((storage/'summary.json').read_text())
        return ((pilot/'cells.spice').read_text(),(pilot/'pair.spice').read_text(),pi['cells'],
            (root/sr['extraction']['netlist']).read_text(),p.cell_definition((bank/'bank.spice').read_text(),p.PN),ci['devices'])

    def test_actual_native_assembly_changes_only_four_positive_buffers_and_preserves_loads(self):
        cells,module,logical,storage,pn,original=self.fixture()
        baseline=p.assemble(cells,module,logical,storage,pn,'baseline')
        matched=p.assemble(cells,module,logical,storage,pn,'matched')
        a=p.observations(*baseline);b=p.observations(*matched);proof=p.preservation(a,b,original)
        self.assertEqual(len(a),644);self.assertEqual(len(b),844);self.assertFalse(proof['new_shared_wire_rc_qualified'])
        self.assertEqual(p.cell_definition(baseline[1],'openlvds_routed_pair_static_phase_release_v2'),
            p.cell_definition(matched[1],'openlvds_routed_pair_static_phase_release_v2'))
        definitions=p.source.native.definitions(matched[0])
        self.assertEqual(definitions[p.BUFFER][0],['A','X','VGND','VPWR'])
        self.assertEqual(definitions[p.BUFFER][1],[['Xrestore0','A','internal_b','VGND','VPWR',p.PN],
            ['Xrestore1','internal_b','X','VGND','VPWR',p.PN]])
        for arow,brow in zip(p.source.native.definitions(baseline[0])[p.CORE][1],definitions[p.CORE][1]):
            self.assertEqual(arow[:-1],brow[:-1])
            self.assertEqual(brow[-1],p.BUFFER if arow[0][1:] in p.ROLES else arow[-1])

    def test_changed_role_master_namespace_or_unrelated_native_terminal_is_rejected(self):
        cells,module,logical,storage,pn,original=self.fixture()
        bad=deepcopy(logical);next(c for c in bad if c['name']=='request_driver')['model']='unexpected_buffer'
        with self.assertRaisesRegex(ValueError,'buffer roles'):p.assemble(cells,module,bad,storage,pn,'matched')
        with self.assertRaises(ValueError):p.assemble(cells,module,logical,storage,pn,'other')
        with self.assertRaisesRegex(ValueError,'namespace or ports'):
            p.assemble(cells,module,logical,storage,pn.replace(' A Y VGND VPWR',' A Y VPWR VGND',1),'matched')
        a=p.observations(*p.assemble(cells,module,logical,storage,pn,'baseline'))
        b=p.observations(*p.assemble(cells,module,logical,storage,pn,'matched'))
        bad=deepcopy(b);d=next(d for d in bad if not any(d['name'].startswith('XD:XR:X'+role+':') for role in p.ROLES))
        d['terminals'][1]+='_changed'
        with self.assertRaisesRegex(ValueError,'not preserved'):p.preservation(a,bad,original)

    def test_every_fixture_retains_original_request_epochs_waveform_limits_and_full_load_probes(self):
        devices=[dict(terminals=['probe_d','probe_g','probe_s','0'])]
        for s in p.specifications():
            text=p.fixture(Path('/unused'),s,devices);spec={k:v for k,v in s.items() if k!='buffer_variant'}
            self.assertEqual(text.replace('OpenLVDS '+p.VERSION,'OpenLVDS '+p.source.baseline.VERSION,1),
                p.source.baseline.fixture(Path('/unused'),spec,devices))
            self.assertIn('.tran 1p 26n 0 1p',text);self.assertIn('3.39n 0 3.41n 1.8',text)
            self.assertIn('22.99n 0 23.01n 1.8',text);self.assertIn('method=gear reltol=1e-4 abstol=1e-12',text)
            self.assertIn('V(probe_g)',text)

    def test_complete_paired_comparison_retains_baseline_failures_without_routed_admission(self):
        rows=[]
        for k,s in enumerate(p.specifications()):
            good=s['buffer_variant']=='matched'
            result=dict(hypothesis_point_checks_passed=good,low_windows=dict(minimum_remaining_low_window_ps=100 if good else -90),
                minimum_clock_low_voltage_margin_v=.1 if good else -.294)
            rows.append(dict(task=dict(id=str(k),spec=s),result=result,error=None))
        r=p.assess(rows);self.assertTrue(r['matched_component_hypothesis_passed']);self.assertFalse(r['baseline_component_hypothesis_passed'])
        self.assertEqual(len(r['pairs']),12)
        for flag in ('actual_shared_counter_timing_pilot_passed','all_pvt_covered','whole_clock_rc_qualified','hardware_warmup_qualified','electrical_qualification_passed','qualified_phy'):
            self.assertFalse(r[flag])
        self.assertIsNone(p.assess(rows[:-1]))
        bad=deepcopy(rows);bad[-1]=bad[0]
        with self.assertRaisesRegex(ValueError,'paired 24-case'):p.assess(bad)
        bad=deepcopy(rows);bad[1]['error']='native failure';self.assertIsNone(p.assess(bad))

    def test_absent_diagnosis_cannot_prepare_or_dispatch_hypothesis(self):
        with patch.object(p,'require_diagnosis',side_effect=ValueError('Complete native cause required')):
            with self.assertRaises(ValueError):p.prepare(Path('/counter'),Path('/bank'),Path('/missing'))

    def test_prepared_native_context_binds_all_twenty_four_original_protocol_decks(self):
        folder=p.ROOT/'build/diagnostics/counter_matched_buffers_v306/f9b748a6ac5c2ee2'
        if not folder.exists():self.skipTest('Prepared matched-buffer native context required')
        m=json.loads((folder/'manifest.json').read_text());i=m['identity']
        self.assertEqual(folder.name,hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16])
        self.assertEqual(i['specs'],p.specifications());self.assertEqual(i['max_workers'],2);self.assertEqual(i['priority'],0)
        self.assertEqual({k:len(v) for k,v in i['devices'].items()},dict(baseline=644,matched=844))
        self.assertFalse(m['qualified_phy']);self.assertFalse(i['preservation']['new_shared_wire_rc_qualified'])
        self.assertEqual(len(m['tasks']),24)
        for name,digest in m['libraries'].items():self.assertEqual(p.sha(folder/name),digest)
        self.assertEqual(p.sha(Path(p.__file__)),i['inputs']['scripts/probe_counter_matched_buffers_v306.py'])
        for task in m['tasks']:
            s=task['spec'];deck=folder/task['id']/'bench.cir'
            self.assertEqual(p.sha(deck),task['deck_sha256'])
            self.assertEqual(deck.read_text(),p.fixture(folder/s['buffer_variant'],s,i['devices'][s['buffer_variant']]))


if __name__=='__main__':unittest.main()
