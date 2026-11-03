from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_native_slew_phases as phase


class NativeSlewPhaseMatrix(unittest.TestCase):
    def data(self,worst=('fs',25)):
        req=json.loads((phase.ROOT/'requirements.json').read_text())
        recipe=dict(version=phase.coverage.VERSION,worst_screened_pvt=list(worst))
        tasks=phase.tasks(req,recipe,phase.pilot.tasks())
        m=dict(tasks=tasks,identity=dict(coverage_recipe=recipe,scope='native phase and logic only'))
        rows=[dict(task=t['id'],spec=t['spec'],error=None,
                   result=dict(passed=True,phase={'filtered_area_difference_v':t['spec'].get('offset_ps',0)*.0007})) for t in tasks]
        return req,m,rows

    def test_complete_native_partition_retains_old_cases_and_deduplicates_additions(self):
        req,m,rows=self.data();actual={phase.coverage.original.signature(t['spec']) for t in m['tasks']}
        old={s for s in phase.coverage.original.required_cases(req) if not s[0] and s[1] in ('phase','logic')}
        self.assertLess(old,actual);self.assertEqual(actual,phase.required(req,m['identity']['coverage_recipe']))
        self.assertEqual(len(actual),len(m['tasks']));self.assertEqual(len({t['id'] for t in m['tasks']}),len(actual))
        self.assertEqual(sum(t['spec']['kind']=='logic' for t in m['tasks']),60)
        self.assertTrue(all(not s[0] and s[1]!='loop' for s in actual))
        for spec in phase.coverage.native_additions(req,('fs',25)):
            self.assertIn(phase.coverage.original.signature(spec),actual)
        donors={phase.coverage.original.signature(t['spec']):t['id'] for t in phase.pilot.tasks()}
        self.assertEqual({t['pilot_task'] for t in m['tasks'] if t['pilot_task']},{v for k,v in donors.items() if k in actual})
        self.assertTrue(all(t['spec']['expected'] is True for t in m['tasks'] if t['spec']['kind']=='logic'))
        self.assertEqual(phase.descriptor(req,m['identity']['coverage_recipe'])['required_cases'],len(actual))
        req2,m2,_=self.data(('ss',40));self.assertEqual(len(m['tasks'])-len(m2['tasks']),28)

    def test_native_balance_monotonicity_and_every_case_must_pass(self):
        req,m,rows=self.data();report=phase.aggregate(m,rows,req)
        self.assertTrue(report['native_phase_matrix_passed']);self.assertFalse(report['physical_admission']);self.assertFalse(report['qualified_phy'])
        for change in ('offset','monotonic','failed','error'):
            bad=deepcopy(rows)
            group=[r for r in bad if r['spec']['kind']=='phase' and (r['spec']['process'],r['spec']['temperature'],r['spec']['mhz'],r['spec']['reference_slew_ps'],r['spec']['feedback_slew_ps'])==('fs',25,400,20,200)]
            if change=='offset':
                for r in group:r['result']['phase']['filtered_area_difference_v']+=.04
            if change=='monotonic':
                next(r for r in group if r['spec']['offset_ps']==0)['result']['phase']['filtered_area_difference_v']=.1
            if change=='failed':bad[0]['result']['passed']=False
            if change=='error':bad[0].update(error='partial',result=None)
            with self.subTest(change=change):self.assertFalse(phase.aggregate(m,bad,req)['native_phase_matrix_passed'])
        for bad in (rows[:-1],rows+[rows[0]]):
            with self.assertRaises(ValueError):phase.aggregate(m,bad,req)
        bad=deepcopy(m);bad['tasks'].pop()
        with self.assertRaises(ValueError):phase.aggregate(bad,rows[:-1],req)

    def test_pilot_reuse_proves_stimulus_observation_and_signature_equivalence(self):
        with tempfile.TemporaryDirectory() as d:
            parent=Path(d);donor=phase.pilot.tasks()[0];f=parent/donor['id'];f.mkdir()
            deck='native fixture\n.include "/old/full.spice"\nVR REF 0 PULSE(0 1.8 5n 20p 20p 1n 2.5n)\n'
            (f/'bench.cir').write_text(deck);aliases={'REF':'REF','REF_FF_CLK_0':'XP:XPHYS:REF.t0'}
            donor=dict(donor,aliases=aliases,deck_sha256=phase.sha(f/'bench.cir'))
            (parent/'manifest.json').write_text(json.dumps({'tasks':[donor]}))
            task=dict(spec=donor['spec'],pilot_task=donor['id'])
            moved=deck.replace('/old/full.spice','/new/full.spice');phase.pilot_equivalence(parent,task,moved,aliases)
            for changed,probes in [(moved.replace('20p','200p'),aliases),(moved,dict(aliases,REF_FF_CLK_0='REF'))]:
                with self.assertRaises(ValueError):phase.pilot_equivalence(parent,task,changed,probes)
            bad=deepcopy(task);bad['spec']['offset_ps']=0
            with self.assertRaises(ValueError):phase.pilot_equivalence(parent,bad,moved,aliases)
            with self.assertRaises(ValueError):phase.normalized(deck+deck)

    def test_stuck_fault_fixture_observes_no_uninstantiated_pfd_gates(self):
        prefix='.lib "/pdk/sky130.lib.spice" ss\n.options device temp=40\n'
        gates={'REF_FF_CLK_0':'XP:XPHYS:REF.t0'}
        for kind in ('phase','logic'):
            task=dict(spec=dict(kind=kind,process='ff',temperature=0))
            with patch.object(phase.pilot,'fixture',return_value=('deck',{})) as build:
                phase.fixture(task,{},gates,prefix,'library','model')
                self.assertEqual(build.call_args.args[2],gates if kind=='phase' else {})
                self.assertIn('" ff\n',build.call_args.args[3]);self.assertIn('temp=0',build.call_args.args[3])

    def test_failed_pilot_and_partial_campaign_never_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(phase.controls,'pilot_gate',side_effect=ValueError('pilot failed')),self.assertRaises(ValueError):phase.prepare(root/'pilot')
            self.assertEqual(list(root.iterdir()),[])
            (root/'manifest.json').write_text('{}');(root/'state.json').write_text('{}')
            with patch.object(phase,'bound',return_value={'tasks':[]}),patch.object(phase,'lease') as lease:
                with self.assertRaisesRegex(ValueError,'no retry'):phase.run(root)
                lease.assert_not_called()

    def test_reused_pilot_evidence_never_obtains_a_simulator_lease(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'matrix';out.mkdir();(out/'manifest.json').write_text('{}')
            (out/'full.spice').write_text('selected native model');(root/'requirements.json').write_text('{}')
            tasks=[dict(id='reused',spec={'kind':'phase'},pilot_task='seed'),dict(id='fresh',spec={'kind':'logic'},pilot_task=None)]
            parent=root/'pilot'/'seed';parent.mkdir(parents=True)
            for n in phase.OUTPUTS:(parent/n).write_text('retained pilot evidence')
            for t in tasks:
                f=out/t['id'];f.mkdir();(f/'bench.cir').write_text('immutable deck')
                t['deck_sha256']=phase.sha(f/'bench.cir')
            m=dict(tasks=tasks,model_sha256=phase.sha(out/'full.spice'),identity={'parent':'pilot','code':{}})
            def simulate(cmd,**kw):
                for n in phase.OUTPUTS:(kw['cwd']/n).write_text('fresh simulation evidence')
                return CompletedProcess(cmd,0,stdout='completed',stderr='')
            with patch.object(phase,'ROOT',root),patch.object(phase,'bound',return_value=m), \
                 patch.object(phase,'lease') as lease,patch.object(phase,'command',return_value=['ngspice']) as command, \
                 patch.object(phase.subprocess,'run',side_effect=simulate) as run, \
                 patch.object(phase,'measure',return_value={'passed':True}) as measure, \
                 patch.object(phase,'aggregate',return_value={'native_phase_matrix_passed':True}):
                phase.run(out)
                self.assertEqual(lease.call_count,1);self.assertEqual(command.call_count,1);self.assertEqual(run.call_count,1)
                self.assertEqual(run.call_args.kwargs['cwd'],out/'fresh')
                self.assertEqual({c.args[0] for c in measure.call_args_list},{parent,out/'fresh'})
                self.assertEqual((parent/'bench.raw').read_text(),'retained pilot evidence')
