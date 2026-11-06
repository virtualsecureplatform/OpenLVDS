# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import ast
import json
import re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_isolated_bank_joint_zero_v258 as p
import isolated_bank_observations_v257 as observations
ROOT=Path(__file__).resolve().parents[1]

class IsolatedZeroScreenTests(unittest.TestCase):
    def test_embedded_cad_admission_code_compiles(self):
        tree=ast.parse(Path(p.__file__).read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='evidence')
        code=next(ast.literal_eval(n.value) for n in function.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='code' for t in n.targets))
        compile(code,'native-cad-admission','exec')
        self.assertIn('qualify_isolated_bank_joint_rc_v255',code)
        self.assertIn("['newly_characterized_junction_devices']!=0",code)

    def test_existing_quarter_slew_and_complete_sample_gates_remain(self):
        base=dict(samples=[dict(rise_delay_ps=550,fall_delay_ps=565),dict(rise_delay_ps=551,fall_delay_ps=566)],static_native_screen_passed=True)
        slews=dict(rise=[232,233],fall=[231,234])
        self.assertTrue(p.assess(base,slews)['joint_rc_zero_screen_passed'])
        slow=dict(base,samples=[dict(rise_delay_ps=640,fall_delay_ps=565),base['samples'][1]])
        self.assertFalse(p.assess(slow,slews)['joint_rc_zero_screen_passed'])
        self.assertFalse(p.assess(base,dict(slews,rise=[251,233]))['joint_rc_zero_screen_passed'])
        self.assertFalse(p.assess(dict(base,static_native_screen_passed=False),slews)['joint_rc_zero_screen_passed'])
        with self.assertRaises(ValueError):p.assess(dict(base,samples=base['samples'][:1]),slews)

    def test_full_native_fixture_preserves_two_pulses_solver_and_all_terminal_probes(self):
        placement=ROOT/'build/diagnostics/isolated_fine_placement_v238/da8cd048ac28c378/manifest.json'
        if not placement.exists():self.skipTest('Native physical fixture required')
        i=json.loads(placement.read_text())['identity'];base=ROOT/'build/diagnostics/isolated_fine_bank_junctions_v246/100682d1c98a6745/ordinary';top=i['graph']['top']
        rc=(base/(top+'.lvs.spice')).read_text().replace('.subckt '+top+'_flat ','.subckt '+top+' ',1).replace('.ends '+top+'_flat','.ends '+top,1)
        o=observations.mapping((base/(top+'.mag')).read_text(),(base/(top+'_flat.ext')).read_text(),rc,i['graph'],i['plan'])
        context=dict(spec=p.spec(),top=top,ports=i['graph']['ports'],observations=o,model='test-model.lib')
        out=ROOT/'build/unused-zero-fixture';text=p.fixture(out,context);old=p.zero.fixture(out,context)
        self.assertEqual(text.replace('OpenLVDS '+p.VERSION,'OpenLVDS '+p.zero.VERSION,1),old)
        probes=set(re.findall(r'V\(([^)]+)\)',text))
        self.assertTrue({n for d in o['devices'] for n in d['terminals'] if n!='0'}<=probes)
        self.assertTrue({g['gate_node'] for g in o['programming_gates']}<=probes)
        self.assertTrue({n['node'] for n in o['data_nodes']}<=probes)
        self.assertIn('.tran 2p 20n 0 2p',text)
        self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',text)
        self.assertEqual(len(o['devices']),1479)

if __name__=='__main__':unittest.main()
