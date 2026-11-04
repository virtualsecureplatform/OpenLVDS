# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_static_phase_backend_v3 as physical
import restrict_macro_rails_v6 as access


class StaticPhaseBackendTests(unittest.TestCase):
    def cells(self):
        c=physical.candidate.circuit;components=c.components
        rc={components.MODELS['nand2_'+str(n)]:dict(info=dict(ports=['A','B','Y','VGND','VPWR'])) for n in [4,8]}
        rc[components.CLOCK_BUFFER]=dict(info=dict(ports=['A','X','VGND','VPWR']))
        for name in [c.previous.previous.NAND2B,*c.previous.MACROS.values(),c.PAIR]:rc[name]=dict(info=dict(ports=['A_N','B','Y','VGND','VPWR']))
        return physical.instances(rc)

    def test_complete_counter_has_one_driver_per_output_net(self):
        cells=self.cells();self.assertEqual(len(cells),19)
        drivers=[c['pins'].get('Y',c['pins'].get('X')) for c in cells]
        self.assertEqual(len(set(drivers)),19)
        self.assertTrue({'PREPARE','RESET_N','request_i'}<=set(drivers))
        self.assertEqual(len({c['model'] for c in cells}),4)

    def test_routing_preserves_clock_and_request_fanout_without_aliasing_prior_states(self):
        cells=self.cells();macros={c['model']:dict(bbox=[-1,-1,57 if c['model']==physical.candidate.circuit.PAIR else 23,20]) for c in cells}
        plan=physical.default_plan();places,qx,bx=physical.placement(cells,macros,plan);points,buses=physical.routing(cells,places,qx,bx,plan)
        self.assertEqual(set(points),set(buses));self.assertEqual(len(points['CLK']),6)
        self.assertEqual({p['x'] for p in points['CLK']},{5})
        low_request=next(p for p in points['request_i'] if p['cell']=='low0_set_pair')
        self.assertEqual(low_request['x'],2)
        for net in ['low0','high1','low1','PREPARE','armed']:
            prior=[p for p in points[net] if '_set' in p['cell']]
            self.assertEqual(len(prior),1);self.assertEqual(prior[0]['x'],8)

    def test_conflicting_native_source_definitions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cells=[];macros={}
            for n in ['a','b']:
                folder=root/n;folder.mkdir();(folder/(n+'.sch.spice')).write_text('.subckt native A Y\nX0 Y A 0 0 nfet w=1\n.ends\n.subckt '+n+' A Y\nXg A Y native\n.ends\n')
                cells.append(dict(name=n,model=n,pins=dict(A='CLK',Y='PREPARE' if n=='a' else 'RESET_N')));macros[n]=dict(folder=n)
            with patch.object(physical,'ROOT',root):
                source=physical.source(cells,macros);self.assertEqual(source.count('.subckt native'),1)
                p=root/'b/b.sch.spice';p.write_text(p.read_text().replace('w=1','w=2'))
                with self.assertRaisesRegex(ValueError,'Conflicting native'):physical.source(cells,macros)

    def test_m5_interface_preserves_all_hidden_routing_shapes(self):
        text='MACRO test\n  PIN Y\n    PORT\n      LAYER met3 ;\n        RECT 0 0 10 0.4 ;\n      LAYER met5 ;\n        RECT 0 2 10 3.6 ;\n    END\n  END Y\nEND test\n'
        changed,view=access.restrict(text,dict(Y=dict(layer='metal5',x_um=.3,y_um=2.8)),dict(Y=('OUTPUT','SIGNAL')))
        self.assertEqual(view['Y']['layer'],'met5');self.assertEqual(access.geometry.geometry(changed),access.geometry.geometry(text))


if __name__=='__main__':unittest.main()
