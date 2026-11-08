# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_input_current_origin_300_v1 as p
import test_two_bank_native_measure_300_v1 as fixtures


class InputOriginPilotTests(unittest.TestCase):
    def test_actual_reference_changes_only_include_and_input_current_card(self):
        out=p.ROOT/'build/unused-input-origin-test';text=p.fixture(out)
        text=text.replace(p.trial.CARD+'\n','',1).replace(f'.include "{out}/bank.spice"',f'.include "{p.PARENT}/bank.spice"')
        self.assertEqual(text,(p.PARENT/'0/bench.cir').read_text())

    def test_full_binary_comparison_preserves_gate_and_dc_failures(self):
        helper=fixtures.RelativeTransportTests();helper.setUp();s=dict(helper.s,stop_ns=40)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            obs=helper.binary_fixture(a,fine=0);helper.binary_fixture(b,fine=0)
            old=p.metrology.measure(a,obs,s,next_coarse=0,next_fine=0)
            new=p.metrology.measure(b,obs,s,next_coarse=0,next_fine=0)
            self.assertTrue(p.compare(a,b,old,new)['passed'])
            new['banks']['next']['terminal_stress'][0]['passed']=False
            self.assertFalse(p.compare(a,b,old,new)['passed'])
            new=p.metrology.measure(b,obs,s,next_coarse=0,next_fine=0)
            names,w=p.validate(b/'bench.raw',set(),40e-9);data=w.copy();del w
            path=b/'bench.raw';header=path.read_bytes().split(b'Binary:\n',1)[0]+b'Binary:\n'
            data[0,names.index('v(first_gate)')]=.003
            path.write_bytes(header+data.astype('<f8').tobytes())
            r=p.compare(a,b,old,new)
            self.assertFalse(r['passed']);self.assertGreater(r['maximum_dc_voltage_error_v'],1e-9)
