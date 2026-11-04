# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_bank_power_access_v2 as access


class PowerAccessTests(unittest.TestCase):
    def fixture(self):
        pins=[];raw=[];hidden=[]
        for n,y in [('A_N',5),('B',6),('Y',7),('VGND',3),('VPWR',9)]:
            rail=[('met4',(0,y,56,y+.8))]
            children=[('met3',(a,y+.1,a+22,y+.7)) for a in [1,30]] if n in ['VGND','VPWR'] else []
            pins.append(f'  PIN {n}\n    PORT\n'+access.lef.render(rail)+f'    END\n  END {n}\n')
            raw.append(f'  PIN {n}\n    PORT\n'+access.lef.render(rail+children)+f'    END\n  END {n}\n')
            hidden+=children
        hidden+=[('met3',(2,12,4,14))]
        return ''.join(pins)+'  OBS\n'+access.lef.render(hidden)+'  END\n',''.join(raw)

    def test_only_four_existing_pg_rails_move_from_obstruction_to_pin(self):
        text,raw=self.fixture();changed,rails=access.adapt(text,raw,[0,0])
        self.assertEqual(access.lef.geometry(text),access.lef.geometry(changed))
        self.assertEqual(set(rails),{'VGND','VPWR'})
        self.assertEqual(sum(map(len,rails.values())),4)
        original={m[1]:m[0] for m in access.lef.PIN.finditer(text)}
        updated={m[1]:m[0] for m in access.lef.PIN.finditer(changed)}
        for n in ['A_N','B','Y']:self.assertEqual(original[n],updated[n])
        self.assertIn('RECT 2.000000 12.000000 4.000000 14.000000',changed)

    def test_missing_duplicate_shifted_and_wrong_supply_rails_are_rejected(self):
        text,raw=self.fixture()
        for bad in [text.replace('RECT 1.000000 3.100000 23.000000 3.700000 ;',''),
                    text.replace('RECT 1.000000 3.100000 23.000000 3.700000 ;',
                                 'RECT 1.000000 3.100000 23.000000 3.700000 ;\n        RECT 1.000000 3.100000 23.000000 3.700000 ;')]:
            with self.assertRaises(ValueError):access.adapt(bad,raw,[0,0])
        with self.assertRaises(ValueError):access.adapt(text,raw,[.1,0])
        with self.assertRaises(ValueError):access.adapt(text,raw.replace('PIN VGND','PIN BAD').replace('END VGND','END BAD'),[0,0])
