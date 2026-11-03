from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dll_analog_frontend_timing as timing


class AnalogFrontendTiming(unittest.TestCase):
    def manifest(self):
        variants=list(timing.dc.policy.VARIANTS)
        tasks=timing.tasks(variants);m=dict(tasks=tasks,identity={'variants':variants,'scope':'source SS40 timing only'})
        rows=[dict(task=t['id'],variant=t['variant'],spec=t['spec'],error=None,
                   result=dict(passed=True,native_phase=dict(phase={'filtered_area_difference_v':t['spec']['offset_ps']*.0007},mean_power_w=.001+variants.index(t['variant'])*.0001))) for t in tasks]
        return m,rows

    def test_all_dc_survivors_both_slews_nine_offsets_known_failures_first(self):
        m,rows=self.manifest();tasks=m['tasks'];self.assertEqual(len(tasks),72)
        self.assertEqual(len({t['id'] for t in tasks}),72)
        self.assertEqual([t['spec']['offset_ps'] for t in tasks[:8]],[50]*4+[-50]*4)
        for v in m['identity']['variants']:
            for sr,sf in timing.pilot.coverage.SLEWS:
                self.assertEqual({t['spec']['offset_ps'] for t in tasks if t['variant']==v and (t['spec']['reference_slew_ps'],t['spec']['feedback_slew_ps'])==(sr,sf)},set(timing.pilot.coverage.SOURCE_OFFSETS))
        for variants in ([],['tail140_w20']*2,['unknown']):
            with self.assertRaises(ValueError):timing.tasks(variants)

    def test_full_native_fixture_adds_one_shared_pair_and_preserves_gate_observations(self):
        model='''.subckt lvds_bias PB NB VDDIO VSS
R0 PB NB 1k
R1 NB VSS 1k
.ends lvds_bias
.subckt openlvds_dll_analog CLK EN P0 P90 P180 P270 FB PD_REF BAD UP DN PB VDDIO VDDD VSS
R0 openlvds_dll_analog__CTRL VSS 1k
R1 openlvds_dll_analog__UF VSS 1k
R2 openlvds_dll_analog__DF VSS 1k
.ends openlvds_dll_analog
.subckt lvds_pfd REF FB RST EN UP DN VDDD VSS
XPHYS REF FB UP DN VDDD VSS physical_pfd
.ends lvds_pfd
.subckt physical_pfd REF FB UP DN VDDD VSS
R0 REF REF.t0 1
R1 REF REF.t1 1
R2 FB FB.t0 1
R3 FB FB.t1 1
.ends physical_pfd
'''
        prefix='native fixture\n.lib "/pdk/sky130.lib.spice" ss\n.include "/old/full.spice"\n.options device temp=40\nVA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n'
        gates={side+str(i):'XP:XPHYS:'+node+'.t'+str(i) for side,node in [('REF_FF_CLK_','REF'),('FB_FF_CLK_','FB')] for i in (0,1)}
        task=timing.tasks(['tail140_w20'])[0];model+=timing.dc.policy.circuit(task['variant'])[0]
        deck,aliases=timing.fixture(task,{},gates,prefix,'/new/model.spice',model)
        self.assertIn('XP REF_FAST FDB_FAST RST VDDD UP DN VDDD 0 lvds_pfd',deck)
        self.assertEqual(deck.count('XF REF FDB REF_FAST FDB_FAST PB VDDIO VDDD 0 '+timing.dc.policy.PAIR),1)
        self.assertEqual(timing.bias_reference_count(deck,model),1)
        self.assertIn('.tran 5p 160n 0 20p',deck);self.assertIn('XA 0 VDDD',deck)
        self.assertTrue(gates.items()<=aliases.items());self.assertIn('XF:VCM',aliases)
        for d in timing.dc.policy.circuit(task['variant'])[1]:
            self.assertTrue(set(d['terminals'])-{'0'}<=set(aliases.values()))
        with patch.object(timing.pilot,'fixture',return_value=('wrong native instance',{})),self.assertRaises(ValueError):
            timing.fixture(task,{},gates,prefix,'/new/model.spice',model)

    def test_every_device_stress_includes_startup_and_reference_must_settle(self):
        variant='tail140_w20';t=np.linspace(0,160e-9,1001)
        nodes={n for d in timing.dc.policy.circuit(variant)[1] for n in d['terminals'] if n!='0'}|{'XF:VCM'}
        signals={n:np.zeros(len(t)) for n in nodes};signals['VDDIO'][:]=3.3;signals['VDDD'][:]=1.8;signals['PB'][:]=2.3;signals['XF:VCM'][:]=.9
        self.assertTrue(timing.frontend_health(t,signals,variant)['passed'])
        bad={n:v.copy() for n,v in signals.items()};bad['XF:XREF:O'][1]=2.1
        self.assertFalse(timing.frontend_health(t,bad,variant)['passed'])
        bad={n:v.copy() for n,v in signals.items()};bad['XF:VCM'][t>120e-9]=.92
        self.assertFalse(timing.frontend_health(t,bad,variant)['passed'])
        with self.assertRaises(ValueError):timing.frontend_health(t[:100],{n:v[:100] for n,v in signals.items()},variant)

    def test_native_phase_conditioned_clocks_and_frontend_health_are_independent(self):
        task=dict(variant='tail140_w20',spec={},aliases={'REF':'REF','FDB':'FDB'})
        wave=np.zeros((2,4));header={'V(REF)':2,'V(FDB)':3}
        for failure in (None,'phase','clock','frontend'):
            with self.subTest(failure=failure),patch.object(timing.pilot,'measure',return_value={'passed':failure!='phase'}), \
                 patch.object(timing.pilot.original,'completed',return_value=(wave,dict(header))), \
                 patch.object(timing.dc.screen,'clock_integrity',return_value=failure!='clock'), \
                 patch.object(timing,'frontend_health',return_value={'passed':failure!='frontend'}):
                self.assertEqual(timing.measure(Path('unused'),task)['passed'],failure is None)

    def test_balance_monotonicity_ranking_and_complete_results_are_required(self):
        m,rows=self.manifest();report=timing.aggregate(m,rows)
        self.assertEqual(report['ranked_survivors'],m['identity']['variants']);self.assertFalse(report['physical_admission']);self.assertFalse(report['qualified_phy'])
        for failure in ('balance','monotonic','failed','error'):
            bad=deepcopy(rows);selected=[r for r in bad if r['variant']=='tail140_w20']
            if failure=='balance':
                for r in selected:r['result']['native_phase']['phase']['filtered_area_difference_v']+=.05
            if failure=='monotonic':
                next(r for r in selected if r['spec']['offset_ps']==0)['result']['native_phase']['phase']['filtered_area_difference_v']=.2
            if failure=='failed':selected[0]['result']['passed']=False
            if failure=='error':selected[0].update(error='incomplete',result=None)
            with self.subTest(failure=failure):self.assertNotIn('tail140_w20',timing.aggregate(m,bad)['ranked_survivors'])
        for bad in (rows[:-1],rows+[rows[0]]):
            with self.assertRaises(ValueError):timing.aggregate(m,bad)

    def test_no_timing_artifacts_before_dc_pass_and_no_partial_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(timing,'admission',side_effect=ValueError('headroom failed')),self.assertRaises(ValueError):timing.prepare(root/'dc',root/'baseline')
            self.assertEqual(list(root.iterdir()),[])
            (root/'manifest.json').write_text('{}');(root/'state.json').write_text('{}')
            with patch.object(timing,'bound',return_value={'tasks':[]}),patch.object(timing,'lease') as lease:
                with self.assertRaisesRegex(ValueError,'no retry'):timing.run(root)
                lease.assert_not_called()

    def test_dc_survivors_and_clock_observations_must_match_the_native_circuit(self):
        with tempfile.TemporaryDirectory() as d,patch.object(timing,'ROOT',Path(d)):
            root=Path(d);parent=root/'build/diagnostics'/timing.dc.NAMESPACE/'dc';parent.mkdir(parents=True)
            base=root/'build/diagnostics'/timing.baseline.NAMESPACE/'b';base.mkdir(parents=True)
            q=root/'q';q.mkdir();(q/'full.spice').write_text('same native circuit');(base/'full.spice').write_text('same native circuit')
            m={'identity':{'qualification_reference':'q'}};bm={'identity':{'qualification':'q'}}
            with patch.object(timing.dc,'verify',return_value={'dc_ready_variants':[]}),patch.object(timing.dc,'bound',return_value=m), \
                 patch.object(timing.baseline,'verify') as verify,self.assertRaises(ValueError):timing.admission(parent,base)
            verify.assert_not_called()
            report={'dc_ready_variants':['tail140_w20']}
            with patch.object(timing.dc,'verify',return_value=report),patch.object(timing.dc,'bound',return_value=m), \
                 patch.object(timing.baseline,'verify',return_value={'baseline_protocol_passed':True}),patch.object(timing.baseline,'bound',return_value=bm):
                self.assertEqual(timing.admission(parent,base),(m,report,bm))
                (base/'full.spice').write_text('other native circuit')
                with self.assertRaises(ValueError):timing.admission(parent,base)
