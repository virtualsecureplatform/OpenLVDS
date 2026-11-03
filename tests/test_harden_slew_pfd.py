from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import harden_slew_pfd as harden
import digital_candidate_rc as legacy


class HardenSlewPFD(unittest.TestCase):
    def test_electrical_validator_uses_system_python_without_nix_python_paths(self):
        parent=harden.ROOT/'build/diagnostics/slew_pfd_source/example'
        result=SimpleNamespace(returncode=0,stdout='{"validated": true}',stderr='')
        with patch.dict(os.environ,{'PYTHONPATH':'wrong-python-3.13','PYTHONHOME':'wrong-home'}),patch.object(harden.subprocess,'run',return_value=result) as process:
            self.assertEqual(harden.source_gate(parent),{'validated':True})
            args,kw=process.call_args
            self.assertEqual(args[0][0],'/usr/bin/python3')
            self.assertNotIn('PYTHONPATH',kw['env']);self.assertNotIn('PYTHONHOME',kw['env'])
        with patch.object(harden.subprocess,'run') as process:
            with self.assertRaises(ValueError):harden.source_gate(harden.ROOT/'other')
            process.assert_not_called()

    def baseline(self):
        rows = '\n'.join(f'ROW ROW_{i} unithd 5520 {10880+i*2720} {"N" if i%2 == 0 else "FS"} DO 193 BY 1 STEP 460 0 ;' for i in range(20))
        pins = '\n'.join(f'- {n} + NET {n} + DIRECTION INPUT + PORT + LAYER met3 ( -300 -300 ) ( 300 300 ) + PLACED ( 300 {47940+i*1360} ) N ;' for i,n in enumerate(('REF','FB')))
        return 'UNITS DISTANCE MICRONS 1000 ;\n'+rows+'\nCOMPONENTS 0 ;\nEND COMPONENTS\nPINS 2 ;\n'+pins+'\nEND PINS\n'

    def fixture(self, root):
        parent = root/'build/diagnostics/slew_pfd_source/source'; parent.mkdir(parents=True)
        original = harden.ROOT
        source_text = harden.policy.source((original/'sky130/experiments/lvds_pfd_area_fast_reset.v').read_text(),'nor4_inv4')
        generated = {'lvds_pfd.v':source_text, 'pfd_blackboxes.v':(original/'sky130/pfd_blackboxes.v').read_text(),
                     'slew_blackboxes.v':harden.policy.blackboxes('nor4_inv4'),'pfd.sdc':'# SDC\n'}
        for n,text in generated.items():(parent/n).write_text(text)
        sm = dict(identity=dict(inputs={},code={},variant='nor4_inv4',policy='pulse-area-fast-reset-slew-v1',coverage_recipe={'version':'dll-slew-repair-v1','worst_screened_pvt':['fs',25]}),files={n:harden.sha(parent/n) for n in generated})
        (parent/'manifest.json').write_text(json.dumps(sm))
        baseline = root/'build/diagnostics/baseline'; baseline.mkdir(parents=True)
        run = root/'build/diagnostics/baseline/run'; (run/'final/def').mkdir(parents=True)
        (run/'final/def/lvds_pfd.def').write_text(self.baseline())
        (baseline/'summary.json').write_text(json.dumps(dict(passed=True,run=str(run.relative_to(root)))))
        lib=root/'pdk.lib';lib.write_text('test collateral\n')
        (baseline/'config.json').write_text(json.dumps(dict(DESIGN_NAME='lvds_pfd',SYNTH_ELABORATE_ONLY=True,LIB={'nom_':[str(lib)]})))
        for n in ('harden_slew_pfd.py','slew_pfd_floorplan.py','receiver_static_diagnosis.py','dll_campaign.py'):
            dest=root/'scripts'/n;dest.parent.mkdir(exist_ok=True);shutil.copyfile(original/'scripts'/n,dest)
        shared=root/'thirdparties/OpenPLL/sky130/sky130_fd_sc_hd_pll_blackbox.v';shared.parent.mkdir(parents=True);shared.write_text('// shared models\n')
        return parent, baseline, sm

    def outputs(self,out):
        target=json.loads((out/'target.json').read_text());masters={name:p['master'] for p in target['pairs'] for name in (p['first'],p['second'])}
        masters.update(clear='sky130_fd_sc_hd__a22oi_4',reset_disable='sky130_fd_sc_hd__nand2_1');cells=[]
        for n,entry in target['manual_global_placements'].items():
            x,y=(round(v*1000) for v in entry['location']);cells.append(f'- {n} {masters[n]} + PLACED ( {x} {y} ) {entry["orientation"]} ;')
        definition=target['pin_template'].replace('COMPONENTS 0 ;\nEND COMPONENTS',f'COMPONENTS {len(cells)} ;\n'+'\n'.join(cells)+'\nEND COMPONENTS')
        texts={'nl/lvds_pfd.nl.v':(out/'inputs/lvds_pfd.v').read_text(),'def/lvds_pfd.def':definition,
               'gds/lvds_pfd.gds':'unit fixture only\n','spice/lvds_pfd.spice':'unit fixture only\n',
               'metrics.json':json.dumps({n:0 for n in harden.DRC})}
        final=harden.run_directory(out)/'final'
        for n,text in texts.items():p=final/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        (out/'flow.log').write_text('unit fixture only\n')
        return final

    def test_source_gate_rejects_incomplete_evidence_before_creating_physical_artifacts(self):
        with tempfile.TemporaryDirectory() as d, patch.object(harden,'source_gate',side_effect=ValueError('pending')):
            root=Path(d)
            with self.assertRaisesRegex(ValueError,'pending'):harden.prepare(root/'source',root/'baseline')
            self.assertEqual(list(root.iterdir()),[])

    def test_captured_archive_contract_and_independent_physical_checks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent,baseline,sm=self.fixture(root)
            with patch.object(harden,'ROOT',root),patch.object(harden,'source_gate',return_value=sm),patch.object(harden,'tools',return_value={'test':'tools'}):
                out=harden.prepare(parent,baseline);m=harden.bound(out);self.assertEqual(harden.prepare(parent,baseline),out)
                self.outputs(out);r=harden.assess(out,m,0)
                self.assertTrue(r['passed']);self.assertTrue(r['geometry']['placement_matched'])
                for key in ('strict_extracted_lvs_verified','route_matching_verified','physical_admission','qualified_phy'):self.assertFalse(r[key])
                with patch.object(legacy,'ROOT',root):self.assertEqual(legacy.captured_inputs(out,r),'lvds_pfd')
                self.assertIn('sky130_fd_sc_hd__nor4_1',(out/'inputs/pfd_blackboxes.v').read_text())

    def test_missing_or_nonzero_drc_tool_failure_and_missing_outputs_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent,baseline,sm=self.fixture(root)
            with patch.object(harden,'ROOT',root),patch.object(harden,'source_gate',return_value=sm),patch.object(harden,'tools',return_value={}):
                out=harden.prepare(parent,baseline);m=harden.bound(out);final=self.outputs(out)
                self.assertFalse(harden.assess(out,m,1)['passed'])
                for value in ({}, {n:False for n in harden.DRC}, {n:1 for n in harden.DRC}):
                    (final/'metrics.json').write_text(json.dumps(value));self.assertFalse(harden.assess(out,m,0)['passed'])
                (final/'metrics.json').write_text(json.dumps({n:0 for n in harden.DRC}))
                (final/'gds/lvds_pfd.gds').write_text('');self.assertFalse(harden.assess(out,m,0)['passed'])

    def test_final_geometry_topology_and_receipt_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent,baseline,sm=self.fixture(root)
            with patch.object(harden,'ROOT',root),patch.object(harden,'source_gate',return_value=sm),patch.object(harden,'tools',return_value={}):
                out=harden.prepare(parent,baseline);m=harden.bound(out);final=self.outputs(out)
                r=dict(harden.assess(out,m,0),manifest_sha256=harden.sha(out/'manifest.json'),files={str(p.relative_to(out)):harden.sha(p) for p in harden.output_files(out)})
                (out/'summary.json').write_text(json.dumps(r));self.assertEqual(harden.verify(out),r)
                nl=final/'nl/lvds_pfd.nl.v';nl.write_text(nl.read_text().replace('.CLK(ref_conditioned)','.CLK(REF)'))
                self.assertFalse(harden.assess(out,m,0)['passed'])
                with self.assertRaises(ValueError):harden.verify(out)

    def test_rehashed_archive_template_change_does_not_inherit_immutable_context(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent,baseline,sm=self.fixture(root)
            with patch.object(harden,'ROOT',root),patch.object(harden,'source_gate',return_value=sm),patch.object(harden,'tools',return_value={}):
                out=harden.prepare(parent,baseline);m=json.loads((out/'manifest.json').read_text())
                p=out/'inputs/pins.def';p.write_text(p.read_text().replace('300 55760','300 55761'));m['files']['inputs/pins.def']=harden.sha(p)
                (out/'manifest.json').write_text(json.dumps(m))
                with self.assertRaises(ValueError):harden.bound(out)

    def test_partial_physical_run_never_restarts_tools(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'manifest.json').write_text('{}');(out/'state.json').write_text('{}')
            with patch.object(harden,'bound',return_value={}),patch.object(harden.subprocess,'run') as process:
                with self.assertRaisesRegex(ValueError,'no retry'):harden.run(out)
                process.assert_not_called()
