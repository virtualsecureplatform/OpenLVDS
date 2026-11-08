# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import two_bank_entry_measure_300_v2 as p
import bank_entry_waveform_300_v2 as waveform
import test_two_bank_native_measure_300_v1 as fixtures
from replay_bank_300_v2 import same


class MatchedReferenceReaderTests(unittest.TestCase):
    def test_complete_100ps_binary_agreement_and_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);helper=fixtures.RelativeTransportTests();helper.setUp()
            obs=helper.binary_fixture(folder,fine=0)
            s=dict(helper.s,input_slew_ps=100,stop_ns=40)
            path=folder/'bench.raw';header=path.read_bytes().split(b'Binary:\n',1)[0]+b'Binary:\n'
            names,w=p.validate(path,set(),40e-9);data=np.array(w);del w
            data[:,names.index('v(in)')]=waveform.evaluate(data[:,names.index('time')]*1e12,s)
            path.write_bytes(header+data.astype('<f8').tobytes())
            a=p.measure(folder,obs,s,next_coarse=0,next_fine=0)
            b=p.measure(folder,obs,s,next_coarse=0,next_fine=0,independent_reader=True)
            self.assertTrue(same(a,b));self.assertTrue(a['two_bank_zero_pilot_passed'])
            self.assertTrue(a['banks']['first']['timing']['ideal_source_waveform_passed'])
            data[0,names.index('v(in)')]=.001;path.write_bytes(header+data.astype('<f8').tobytes())
            a=p.measure(folder,obs,s,next_coarse=0,next_fine=0)
            self.assertFalse(a['banks']['first']['timing']['ideal_source_waveform_passed'])
            self.assertFalse(a['two_bank_zero_pilot_passed'])
