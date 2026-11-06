# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json
import shlex
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regular_regenerated_observations_v285 as p
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/diagnostics/regular_regenerated_junctions_v276/ca85f4dd7ca7a27a/ordinary'
PLACEMENT=ROOT/'build/diagnostics/regular_regenerated_placement_v272/82dc7493ef40f70d/manifest.json'

@unittest.skipUnless(PLACEMENT.exists() and BASE.exists(),'Real native geometry fixture required')
class IsolatedObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        i=json.loads(PLACEMENT.read_text())['identity'];cls.graph=i['graph'];cls.plan=i['plan'];cls.mag=(BASE/(p.TOP+'.mag')).read_text()
        cls.ext=(BASE/(p.TOP+'_flat.ext')).read_text();cls.rc=(BASE/(p.TOP+'.lvs.spice')).read_text().replace('.subckt '+p.TOP+'_flat ','.subckt '+p.TOP+' ',1).replace('.ends '+p.TOP+'_flat','.ends '+p.TOP,1)
        cls.o=p.mapping(cls.mag,cls.ext,cls.rc,cls.graph,cls.plan)

    def test_all_native_devices_typed_gates_controls_and_data_nodes_are_observed(self):
        o=self.o
        self.assertEqual((len(o['devices']),len(o['programming_gates']),len(o['logical_controls']),o['observed_canonical_nets'],o['physical_instances']),(1529,173,86,152,353))
        self.assertEqual({x['data_net'] for x in o['data_nodes']},{'selected','fine_node','restored_b'})
        self.assertTrue(all(len(d['terminals'])==4 and d['limit_v']==1.95 for d in o['devices']))
        self.assertFalse(o['rc_model_changed'])

    def test_separated_programming_gate_keeps_its_own_voltage_node(self):
        gate=self.o['programming_gates'][0];name=gate['device'].split(':')[-1];lines=self.rc.splitlines(keepends=True)
        for k,line in enumerate(lines):
            words=line.split()
            if words and words[0]==name:
                old=words[2];new=old+'.t9001';words[2]=new;lines[k]=' '.join(words)+'\n';break
        else:self.fail('Actual native programming card missing')
        rc=''.join(lines).replace('.ends',f'Robserve {new} {old} 12\n.ends',1)
        result=p.mapping(self.mag,self.ext,rc,self.graph,self.plan)
        actual=next(g for g in result['programming_gates'] if g['device']==gate['device'])
        self.assertEqual(actual['control'],gate['control']);self.assertEqual(actual['gate_node'],'XD:'+new)
        self.assertNotEqual(actual['gate_node'],gate['gate_node'])

    def test_missing_real_alias_or_short_between_isolated_data_nets_is_rejected(self):
        alias=self.o['magic_instance_names']['u_fine_isolate']+'.A'
        ext='\n'.join(line for line in self.ext.splitlines() if not (line.startswith(('node ','equiv ','port ')) and alias in shlex.split(line)[1:]))+'\n'
        with self.assertRaisesRegex(ValueError,'Missing native extraction alias'):
            p.mapping(self.mag,ext,self.rc,self.graph,self.plan)
        node_a=next(x['node'][3:] for x in self.o['data_nodes'] if x['data_net']=='selected')
        node_b=next(x['node'][3:] for x in self.o['data_nodes'] if x['data_net']=='fine_node')
        rc=self.rc.replace('.ends',f'Rshort {node_a} {node_b} 1\n.ends',1)
        with self.assertRaisesRegex(ValueError,'join different logical nets'):
            p.mapping(self.mag,self.ext,rc,self.graph,self.plan)

    def test_load_bypass_or_programming_connection_change_is_rejected(self):
        for name,pin,net in [('u_fine_unit0','A','selected'),('u_fine_unit0','CTRL','fine1'),('u_fine_isolate','Y','OUT'),('u_fine_regenerate0','Y','OUT'),('u_fine_regenerate1','A','fine_node')]:
            g=deepcopy(self.graph);next(c for c in g['cells'] if c['name']==name)['pins'][pin]=net
            with self.assertRaises(ValueError):p.mapping(self.mag,self.ext,self.rc,g,self.plan)

if __name__=='__main__':unittest.main()
