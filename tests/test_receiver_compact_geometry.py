from pathlib import Path
import json,re,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_compact_geometry as compact
import layout_receiver_compact as build
from layout import circuits,flatten,primitive_key,schematic_parameters
from receiver_lvt_pair_experiment import source_variant

class CompactReceiver(unittest.TestCase):
 def test_folded_geometry_preserves_devices_and_public_ports(self):
  text=source_variant((Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text(),True)
  ports,devices=flatten(circuits(text),'openlvds_receiver_core')
  cells={primitive_key(d):('fixture',dict(bbox=[-2,-2,2,10],ports={
      'D':('metal1',-1,3),'G':('metal1',0,3),'S':('metal1',1,3),'B':('locali',-1,-1),
      'R1':('metal1',-1,1),'R2':('metal1',1,1)})) for d in devices}
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);info=compact.draw_macro(folder,'openlvds_receiver_core',ports,devices,cells)
   self.assertEqual(info['devices'],len(devices));self.assertEqual(set(info['ports']),set(ports))
   mag=(folder/'openlvds_receiver_core.mag').read_text()
   ys=re.findall(r'transform 1 0 \d+ 0 1 (\d+)',mag);self.assertGreater(len(set(ys)),1)
   rows=circuits((folder/'openlvds_receiver_core.sch.spice').read_text())['openlvds_receiver_core'][1]
   expected=sorted((d['model'],tuple(d['nodes']),tuple(sorted(schematic_parameters(d).items()))) for d in devices)
   self.assertEqual(sorted((m,tuple(ns),tuple(sorted(ps.items()))) for _,ns,m,ps in rows),expected)
 def test_critical_cluster_follows_frontend_and_monitor_is_separate(self):
  text=source_variant((Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text(),True)
  _,devices=flatten(circuits(text),'openlvds_receiver_core');ordered=compact.ordered(devices)
  self.assertIn('__XTRACK__',ordered[0]['name'])
  first=next(i for i,d in enumerate(ordered) if compact.critical(d))
  self.assertTrue(all(compact.critical(d) for d in ordered[first:]))
  self.assertTrue(all(compact.critical(d) for d in devices if any(n.endswith(('__PP','__PN')) for n in d['nodes'])))
  self.assertEqual(sorted(d['name'] for d in ordered),sorted(d['name'] for d in devices))
 def test_missing_pilot_refuses_before_source_or_layout_execution(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(build,'ROOT',Path(tmp)),patch.object(build.source,'run') as source,patch.object(build.physical,'build') as physical:
   p=Path(tmp)/'build/diagnostics/receiver_lvt_pair_matrix/example';p.mkdir(parents=True)
   children=[dict(root='missing',process=p,temperature=t) for p,t in [('tt',25),('sf',40),('fs',40)]]
   (p/'manifest.json').write_text(json.dumps(dict(identity=dict(children=children))))
   with self.assertRaisesRegex(ValueError,'Complete all three'):build.build(p)
   source.assert_not_called();physical.assert_not_called()
