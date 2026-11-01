# SPDX-License-Identifier: GPL-3.0-only
import ast
import inspect
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_bus_priority as candidate


class ReceiverBusPriority(unittest.TestCase):
    def test_only_the_guarded_routing_assignment_changes(self):
        source=inspect.getsource(candidate.layout.draw_macro)
        original=ast.parse(source);changed=candidate.router_tree(source)
        previous=next(n for n in ast.walk(original) if isinstance(n,ast.Assign) and any(
            isinstance(t,ast.Name) and t.id=='net_order' for t in n.targets))
        following=next(n for n in ast.walk(changed) if isinstance(n,ast.Assign) and any(
            isinstance(t,ast.Name) and t.id=='net_order' for t in n.targets))
        self.assertEqual(ast.dump(following.value),ast.dump(ast.parse('_receiver_bus_order(ports,internal)',mode='eval').body))
        following.value=previous.value
        self.assertEqual(ast.dump(changed),ast.dump(original))
        with self.assertRaisesRegex(ValueError,'routing assignment'):
            candidate.router_tree(source.replace('net_order=list(ports)+sorted','net_order=sorted(ports)+sorted'))

    def test_all_public_and_internal_nets_retained_exactly_once(self):
        ports=['INP','INN','Q','VSS'];critical=[candidate.TOP+'__'+n for n in candidate.SENSITIVE]
        internal=set(critical+['z_extra','a_extra'])
        result=candidate.bus_order(ports,internal)
        self.assertEqual(result,ports+critical+['a_extra','z_extra'])
        self.assertEqual(len(result),len(set(result)))
        for nets in [internal-{critical[0]},internal|{'Q'}]:
            with self.assertRaises(ValueError):candidate.bus_order(ports,nets)

    def test_drawing_keeps_devices_schematic_public_pins_width_and_height(self):
        ports='INP INN Q VREF PB NB VDDIO VDDD VSS'.split()
        nets=ports+[candidate.TOP+'__'+n for n in candidate.SENSITIVE]
        model='sky130_fd_pr__res_high_po_0p35'
        devices=[dict(name=candidate.TOP+'__R'+str(i),nodes=[n,'VSS','VSS'],model=model,
                      params=dict(w='0.35',l='1.25')) for i,n in enumerate(nets)]
        library={(model,.35,1.25):('cell',dict(bbox=[-1,-1,1,1],ports={
            'R1':('metal1',-.5,0),'R2':('metal1',.5,0),'B':('metal1',0,-.5)}))}
        with tempfile.TemporaryDirectory() as temp:
            old=Path(temp)/'old';new=Path(temp)/'new';old.mkdir();new.mkdir()
            baseline=candidate.layout.draw_macro(old,candidate.TOP,ports,devices,library)
            actual=candidate.router()(new,candidate.TOP,ports,devices,library)
            self.assertEqual(actual,baseline)
            self.assertEqual((old/(candidate.TOP+'.sch.spice')).read_bytes(),(new/(candidate.TOP+'.sch.spice')).read_bytes())
            a=(old/(candidate.TOP+'.mag')).read_text();b=(new/(candidate.TOP+'.mag')).read_text()
            uses=r'(?m)^use [^\n]+\ntimestamp 0\ntransform [^\n]+\nbox [^\n]+'
            self.assertEqual(re.findall(uses,a),re.findall(uses,b))
            def bus_y(text):
                return int(next(line.split()[3] for line in text.splitlines() if line.startswith('rlabel ') and line.endswith(candidate.TOP+'__PP')))
            self.assertGreater(bus_y(b),bus_y(a))


if __name__=='__main__':unittest.main()
