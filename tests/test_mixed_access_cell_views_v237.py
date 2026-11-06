# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import copy
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import mixed_access_cell_views_v237 as views

LEF='''MACRO driver
  CLASS BLOCK ;
  ORIGIN 0 0 ;
  SIZE 8 BY 8 ;
  PIN A
    DIRECTION INPUT ;
    USE SIGNAL ;
    PORT
      LAYER met4 ;
        RECT 1 1 2 7 ;
    END
  END A
  PIN Y
    DIRECTION OUTPUT ;
    USE SIGNAL ;
    PORT
      LAYER met3 ;
        RECT 3 1 7 2 ;
    END
  END Y
END driver
'''

class MixedAccessTests(unittest.TestCase):
    def render(self,layers):
        return views.integration_lef(LEF,'driver',['A','Y'],dict(A='input',Y='output'),
            dict(A='A',Y='Y'),dict(A=(1.5,4),Y=(4,1.5)),[2,3],[10,11],
            [('met4',(3,4,4,10)),('met3',(5,4,9,5))],layers)

    def test_access_layer_and_translated_metal_are_preserved(self):
        text,pins=self.render(dict(A='met4',Y='met3'))
        self.assertEqual(pins['A']['shapes'],[('met4',(3,4,4,10))])
        self.assertEqual(pins['Y']['shapes'],[('met3',(5,4,9,5))])
        info=views.description(text,'driver')
        self.assertEqual(info['origin'],[0,0])
        self.assertEqual(info['pins']['A'],pins['A']['shapes'])
        # Same-layer keepouts exclude the actual public access. No hidden
        # obstruction is created over either of these exact rectangles.
        obs=[s for m in views.geometry.OBS.finditer(text) for s in views.geometry.rectangles(m[1])]
        self.assertEqual(obs,[])

    def test_m3_substitution_for_actual_m4_access_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'unique designated native access'):
            self.render(dict(A='met3',Y='met3'))

try:
    import klayout.db as db
except ImportError:
    db=None

@unittest.skipUnless(db,'KLayout required for native manufacturing masks')
class NativeViewsTests(unittest.TestCase):
    def test_real_mixed_layer_driver_masks_and_accesses(self):
        import build_isolated_fine_cell_views_v236 as producer
        specs,_=producer.sources()
        with tempfile.TemporaryDirectory(dir=producer.ROOT/'build') as tmp:
            for model,spec in specs.items():
                lib,top,lef,record=views.normalize(spec,model)
                file=Path(tmp)/(model+'.gds');opts=db.SaveLayoutOptions();opts.select_cell(top.cell_index());lib.write(str(file),opts)
                lp=file.with_suffix('.lef');lp.write_text(lef)
                self.assertTrue(producer.audit(spec,model,file,lp,record)['all_native_masks_preserved_under_translation'])
                expected='met4' if 'discharge' in model else 'met3'
                self.assertEqual(record['pins']['A']['shapes'][0][0],expected)
                bad=copy.deepcopy(spec);bad['access_layers']['A']='met3' if expected=='met4' else 'met4'
                with self.assertRaisesRegex(ValueError,'public label|public port|native access'):
                    views.normalize(bad,model+'_bad')

if __name__=='__main__':unittest.main()
