# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_mux_return_v2 as circuit
import verify_dcdl_mux_return_v2 as verification


class DcdlMuxReturnTests(unittest.TestCase):
    def test_every_coarse_code_preserves_polarity_and_selects_its_actual_depth(self):
        for coarse in range(16):
            for level in [False,True]:
                values={'IN':(level,set()),**{f'C{i}':(i<coarse,set()) for i in range(15)}}
                pending=circuit.core_instances()
                while pending:
                    remaining=[]
                    for cell in pending:
                        p=cell['pins'];m=cell['model'];inputs=['A'] if m.endswith(('buf_4','inv_4')) else ['A0','A1','S'] if m.endswith('mux2i_4') else ['A','B']
                        if not all(p[n] in values for n in inputs):remaining.append(cell);continue
                        if m.endswith('buf_4'):result=values[p['A']];out=p['X']
                        elif m.endswith('inv_4'):v,d=values[p['A']];result=(not v,d);out=p['Y']
                        elif m.endswith('mux2i_4'):
                            selected=p['A1' if values[p['S']][0] else 'A0'];v,d=values[selected];result=(not v,d);out=p['Y']
                        else:
                            a,dep=values[p['A']];b=values[p['B']][0]
                            result=(not(a and b),(dep|{int(cell['name'].removeprefix('forward'))}) if b else set());out=p['Y']
                        if out in values:self.assertEqual(values[out],result)
                        values[out]=result
                    self.assertLess(len(remaining),len(pending));pending=remaining
                self.assertEqual(values['OUT'],(level,set(range(coarse))))
        cells=circuit.core_instances()
        self.assertEqual(len([c for c in cells if c['name'].startswith('tail')]),4)
        self.assertEqual(len([c for c in cells if c['name'].startswith('return0_')]),4)
        self.assertEqual(len([c for c in circuit.instances() if c['model']==circuit.fine.NAME]),31)

    def test_missing_native_interface_is_rejected_and_rom_admission_remains_closed(self):
        with self.assertRaisesRegex(ValueError,'Missing native'):circuit.source({})
        rows=[]
        for spec in verification.pilot.specifications():
            delay=300 if spec['fine']==0 and spec['coarse']==0 else 550 if spec['fine']==31 else 600
            rows.append(dict(task=dict(spec=spec),result=dict(samples=[dict(rise_delay_ps=delay,fall_delay_ps=delay)],native_pulse_passed=True)))
        self.assertFalse(any(g['sparse_feasibility_passed'] for g in verification.assess(rows)))
        with self.assertRaisesRegex(ValueError,'Incomplete'):verification.assess(rows[:-1])


if __name__=='__main__':unittest.main()
