# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import klayout.db
except ImportError:
    CAD=False
else:
    CAD=True


@unittest.skipUnless(CAD,'KLayout required by native route producer')
class RegularPairRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import route_regular_regenerated_bank_v278 as route
        cls.r=route
        cls.placed=route.ROOT/'build/diagnostics/regular_regenerated_placement_v272/82dc7493ef40f70d'
        cls.interface=route.ROOT/'build/diagnostics/regular_regenerated_routing_interface_v274/b41db4edac628761'
        cls.pi=json.loads((cls.placed/'manifest.json').read_text())['identity']
        cls.ii=json.loads((cls.interface/'manifest.json').read_text())['identity']

    def contract(self):
        return dict(self.r.interface.contract(self.pi),input_proxy=self.r.input_proxy(self.placed,self.pi),
                    fixed_bus_terminals_retained_for_routing=True)

    def write(self,out,name,rows):
        (out/name).write_text(''.join('\t'.join(map(str,row))+'\n' for row in rows))

    def test_incomplete_native_pilot_is_rejected_without_creating_route_outputs(self):
        with tempfile.TemporaryDirectory(dir=self.r.ROOT/'build') as directory:
            parent=Path(directory);(parent/'state.json').write_text(json.dumps(dict(status='running',qualified_phy=False)))
            with self.assertRaisesRegex(ValueError,'complete error-free four-point regular-pair'):
                self.r.native_gate(parent)
            self.assertEqual({p.name for p in parent.iterdir()},{'state.json'})

    def test_all_93_fixed_bus_terms_remain_native_and_input_proxy_is_real_metal(self):
        c=self.contract();out=Path('/unused-native-route-fixture')
        text=self.r.tcl(self.placed,out,c)
        self.assertIn('detailed_route -output_drc',text)
        self.assertEqual(text.count('# Native fixed-bus terminal remains connected'),93)
        self.assertEqual(text.count('$term disconnect'),1)
        self.assertIn('odb::dbBox_create $input_pin $input_layer {*}$input_original_coords',text)
        self.assertTrue(c['input_proxy']['existing_native_metal_verified'])
        self.assertIn('restored_b',c['regular_wire_nets'])
        bad=deepcopy(c);bad['buses'][0]['terminals'].pop()
        with self.assertRaisesRegex(ValueError,'disconnection inventory'):self.r.tcl(self.placed,out,bad)

    def test_route_coverage_requires_regular_pair_intermediate_wire_and_native_bus_connections(self):
        c=self.contract()
        with tempfile.TemporaryDirectory(dir=self.r.ROOT/'build') as directory:
            out=Path(directory)
            for kind in ['connections','ports','boxes','masters','buses']:
                shutil.copyfile(self.interface/('after_'+kind+'.tsv'),out/('after_'+kind+'.tsv'))
            wanted=[(cell['name'],pin,net) for cell in self.pi['plan']['cells'] for pin,net in cell['pins'].items()]
            self.write(out,'adapted_connections.tsv',wanted)
            proxy=c['input_proxy']
            self.write(out,'adapted_boxes.tsv',[('PORT','IN','FIRM',proxy['layer'],*[round(v*1000) for v in proxy['rect']])])
            nets=[list(row) for row in self.r.interface.rows(self.interface,'after_nets.tsv')]
            for row in nets:
                if row[0] in self.ii['contract']['regular_wire_nets']:row[3]='1'
            self.write(out,'after_nets.tsv',nets)
            identity=dict(parent=str(self.interface.relative_to(self.r.ROOT)),contract=c)
            result=self.r.check(out,identity,self.ii)
            self.assertTrue(result['all_93_fixed_bus_terminals_retained'])
            self.assertTrue(result['physical_connectivity_requires_native_lvs'])
            next(row for row in nets if row[0]=='restored_b')[3]='0';self.write(out,'after_nets.tsv',nets)
            with self.assertRaisesRegex(ValueError,'Missing regular route: restored_b'):self.r.check(out,identity,self.ii)


if __name__=='__main__':unittest.main()
