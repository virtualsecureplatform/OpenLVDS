# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_regular_regenerated_routing_interface_v274 as interface
import verify_regular_regenerated_routing_v275 as stored

PARENT=interface.ROOT/'build/diagnostics/regular_regenerated_placement_v272/82dc7493ef40f70d'


@unittest.skipUnless((PARENT/'manifest.json').exists(),'Native regular-pair placement required')
class RegularPairRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.i=json.loads((PARENT/'manifest.json').read_text())['identity']

    def write(self,folder,name,rows):
        (folder/name).write_text(''.join('\t'.join(map(str,row))+'\n' for row in rows))

    def snapshots(self,out):
        c=interface.contract(self.i);wanted=[(cell['name'],pin,net) for cell in self.i['plan']['cells'] for pin,net in cell['pins'].items()]
        ports=[(p,'OUTPUT' if p=='OUT' else 'INOUT' if p in ('VPWR','VGND') else 'INPUT',
                'POWER' if p=='VPWR' else 'GROUND' if p=='VGND' else 'SIGNAL',p) for p in self.i['graph']['ports']]
        # A synthetic record fixture tests verifier fault rejection. Actual
        # database/model/metal coverage is checked by the producer separately.
        for prefix in ('before','after'):
            for kind in ('connections','ports','boxes','masters','nets','buses'):
                self.write(out,prefix+'_'+kind+'.tsv',wanted if kind=='connections' else ports if kind=='ports' else [])
        removed={(name,pin) for bus in c['buses'] for name,pin in bus['terminals']}
        self.write(out,'adapted_connections.tsv',[(a,b,'NULL' if (a,b) in removed else net) for a,b,net in wanted])
        self.write(out,'terminal_routing.tsv',[(a,b,'1') for a,b,net in wanted])
        self.write(out,'adapted_ports.tsv',[*ports,*[(b['proxy'],'INPUT','SIGNAL',b['net']) for b in c['buses']]])
        self.write(out,'proxy_shapes.tsv',[(b['proxy'],b['layer'],*[round(v*1000) for v in b['rect']]) for b in c['buses']])
        self.write(out,'adapted_buses.tsv',[])
        return dict(contract=c)

    def test_native_three_stage_m4_path_and_exact_93_fixed_terminals(self):
        c=interface.contract(self.i)
        self.assertEqual(sum(len(b['terminals']) for b in c['buses']),93)
        self.assertEqual(len(c['root_outputs']),8)
        self.assertEqual(set(c['m4_driver_data_connections']),{'u_fine_isolate','u_fine_regenerate0','u_fine_regenerate1'})
        self.assertTrue({'selected','fine_node','restored_b'}<=set(c['regular_wire_nets']))
        self.assertNotIn('OUT',c['regular_wire_nets'])
        text=interface.adapter(PARENT,Path('/example'),c)
        self.assertEqual(text.count('$term disconnect'),94)
        self.assertIn('$out_net clearSpecial',text)
        self.assertNotIn('@ADAPT_BUSES@',text)

    def test_wrong_stage_supply_intermediate_net_or_pin_layer_is_rejected(self):
        for name,pin,net in [('u_fine_regenerate0','Y','fine_node'),('u_fine_regenerate1','A','fine_node'),('u_fine_regenerate1','VPWR','VGND')]:
            bad=deepcopy(self.i);next(c for c in bad['plan']['cells'] if c['name']==name)['pins'][pin]=net
            with self.assertRaisesRegex(ValueError,'driver path or supplies'):interface.contract(bad)
        bad=deepcopy(self.i);bad['records'][interface.design.DRIVER]['pins']['Y']['shapes'][0][0]='met3'
        with self.assertRaisesRegex(ValueError,'actual M4'):interface.contract(bad)

    def test_exact_roundtrip_and_all_driver_data_pins_remain_required(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);identity=self.snapshots(out);r=interface.verify(out,identity,self.i)
            self.assertTrue(r['all_three_m4_driver_paths_retained']);self.assertEqual(r['fixed_bus_terminal_count'],93)
            self.assertFalse(r['routed']);self.assertFalse(r['timing_candidate_admitted'])
            text=(out/'adapted_connections.tsv').read_text().replace('u_fine_regenerate1\tA\trestored_b','u_fine_regenerate1\tA\tNULL')
            (out/'adapted_connections.tsv').write_text(text)
            # Even a false shapeless-pin report cannot permit loss of the
            # mandatory M4 pair input.
            (out/'terminal_routing.tsv').write_text((out/'terminal_routing.tsv').read_text().replace('u_fine_regenerate1\tA\t1','u_fine_regenerate1\tA\t0'))
            with self.assertRaisesRegex(ValueError,'M4 regular-pair stage'):interface.verify(out,identity,self.i)

    def test_shifted_proxy_or_changed_restored_master_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);identity=self.snapshots(out)
            rows=[list(v) for v in interface.rows(out,'proxy_shapes.tsv')];rows[0][2]=str(int(rows[0][2])+1000)
            self.write(out,'proxy_shapes.tsv',rows)
            with self.assertRaisesRegex(ValueError,'fixed metal'):interface.verify(out,identity,self.i)
            identity=self.snapshots(out);self.write(out,'after_masters.tsv',[('changed_master',)])
            with self.assertRaisesRegex(ValueError,'changed masters'):interface.verify(out,identity,self.i)

    def test_stored_record_comparison_rejects_new_pair_endpoint_change(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            for kind in stored.KINDS:
                self.write(out,'stored_'+kind+'.tsv',[('native',kind)])
                self.write(out,'expected_'+kind+'.tsv',[('native',kind)])
            self.assertEqual(stored.differences(out,out,'expected'),[])
            self.write(out,'stored_connections.tsv',[('u_fine_regenerate0','Y','fine_node')])
            self.assertEqual(stored.differences(out,out,'expected'),['connections'])

    def test_actual_saved_interface_reproduces_native_roundtrip_and_output_hashes(self):
        parent=interface.ROOT/'build/diagnostics/regular_regenerated_routing_interface_v274/b41db4edac628761'
        if not (parent/'summary.json').exists():self.skipTest('Completed native interface unavailable')
        report=json.loads((parent/'summary.json').read_text())
        identity=json.loads((parent/'manifest.json').read_text())['identity']
        self.assertEqual(json.loads((parent/'state.json').read_text()),dict(status='complete',passed=True,qualified_phy=False))
        self.assertTrue(report['interface_preflight_passed']);self.assertEqual(report['returncode'],0)
        self.assertTrue(all(interface.sha(parent/n)==h for n,h in report['files'].items()))
        self.assertEqual(interface.verify(parent,identity,self.i),report['result'])
        self.assertEqual(report['result']['instances'],353);self.assertEqual(report['result']['fixed_bus_terminal_count'],93)
        self.assertTrue(report['result']['all_three_m4_driver_paths_retained'])
        self.assertFalse(report['routed']);self.assertFalse(report['joint_rc_extracted']);self.assertFalse(report['qualified_phy'])


if __name__=='__main__':unittest.main()
