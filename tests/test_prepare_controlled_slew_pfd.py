import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_controlled_slew_pfd as prepare
import prepare_slew_pfd as original
import qualify_slew_frontend_controls as controls


class ControlledPhysicalSource(unittest.TestCase):
    def test_failed_controls_and_legacy_source_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'build/diagnostics/slew_frontend_controls/example';p.mkdir(parents=True)
            with patch.object(prepare,'ROOT',root),patch.object(controls,'verify',return_value={'source_controls_passed':False,'ranked_survivors':[]}),self.assertRaisesRegex(ValueError,'all-PVT'):prepare.controls_gate(p)
        with patch.object(original,'bound',return_value={'identity':{}}),self.assertRaisesRegex(ValueError,'admission profile'):prepare.bound(prepare.ROOT/'source')

    def test_physical_profile_requires_controlled_validator_and_restores_on_exception(self):
        old=prepare.physical.source_gate
        response=SimpleNamespace(returncode=0,stdout='{"valid":true}',stderr='')
        parent=prepare.ROOT/'build/diagnostics/slew_pfd_source/example'
        with patch.dict(os.environ,{'PYTHONPATH':'bad-nix-python','PYTHONHOME':'bad-home'}),patch.object(prepare.subprocess,'run',return_value=response) as run:
            with self.assertRaisesRegex(RuntimeError,'test exit'):
                with prepare.physical_profile():
                    self.assertEqual(prepare.physical.source_gate(parent),{'valid':True})
                    args,kw=run.call_args;self.assertEqual(args[0][0],'/usr/bin/python3');self.assertIn('prepare_controlled_slew_pfd.py',args[0][1])
                    self.assertNotIn('PYTHONPATH',kw['env']);self.assertNotIn('PYTHONHOME',kw['env'])
                    raise RuntimeError('test exit')
            self.assertIs(prepare.physical.source_gate,old)

    def test_source_selection_filters_controls_and_preserves_actual_worst_corner(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);oldroot=prepare.ROOT
            for n in ['sky130/experiments/lvds_pfd_area_fast_reset.v','sky130/pfd_blackboxes.v','constraints/pfd.sdc',
                      'thirdparties/OpenPLL/sky130/sky130_fd_sc_hd_pll_blackbox.v',
                      *['scripts/'+p for p in ['prepare_controlled_slew_pfd.py','prepare_slew_pfd.py','pfd_slew_policy.py','pfd_fast_reset_policy.py','physical_policy.py']]]:
                dest=root/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(oldroot/n,dest)
            parent=root/'build/diagnostics/dll_slew_expansion/e';parent.mkdir(parents=True)
            report=dict(ranked_survivors=['clkbuf_4','clkbuf_8'],candidates=[dict(variant=v,passed=True,worst_screened_pvt=w) for v,w in [('clkbuf_4',['ss',40]),('clkbuf_8',['fs',25])]])
            (parent/'summary.json').write_text(json.dumps(report))
            ctrl=root/'build/diagnostics/slew_frontend_controls/c';ctrl.mkdir(parents=True)
            for n in ['manifest.json','summary.json']:(ctrl/n).write_text('{}')
            cm=dict(identity=dict(parent=str(parent.relative_to(root)),inputs={str((parent/'summary.json').relative_to(root)):prepare.sha(parent/'summary.json')},code={}),tasks=[])
            r=dict(source_controls_passed=True,ranked_survivors=['clkbuf_8'])
            with patch.object(prepare,'ROOT',root),patch.object(original,'ROOT',root),patch.object(prepare,'controls_gate',return_value=(cm,r)):
                out=prepare.prepare(ctrl);m=prepare.bound(out)
                self.assertEqual(m['identity']['variant'],'clkbuf_8');self.assertEqual(m['identity']['coverage_recipe']['worst_screened_pvt'],['fs',25])
                self.assertEqual(m['identity']['admission_profile'],prepare.PROFILE);self.assertFalse(m['physical_admission'])
                self.assertEqual(prepare.prepare(ctrl),out)
