# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import matched_entry_materials_300_v1 as p
from regenerated_bank_periodic_measure_v67 import crossings


class MatchedEntryTests(unittest.TestCase):
    def test_old_boundary_waveforms_preserved_and_100ps_reference_exact(self):
        base=dict(frequency_mhz=310,cycles=8,stop_ns=40)
        for slew in (20,250):
            for duty in (.4,.5,.6):
                s=dict(base,input_slew_ps=slew,duty=duty)
                self.assertEqual(p.waveform.points(s),p.entry.waveform.points(s))
                self.assertEqual(p.waveform.source(s),p.entry.waveform.source(s))
        s=dict(base,input_slew_ps=100,duty=.6);t=np.arange(0,40001,dtype=float)
        v=p.waveform.evaluate(t,s)
        np.testing.assert_allclose(v,p.waveform.evaluate_independent(t,s),atol=1e-12,rtol=0)
        for up in (True,False):
            a=crossings(t,v,.18,up);b=crossings(t,v,1.62,up)
            self.assertEqual(len(a),8);np.testing.assert_allclose(np.abs(np.array(a)-b),100,atol=1e-6)

    def test_actual_matched_pair_changes_only_source_and_declared_current(self):
        source=p.entry.SOURCE;parent=p.entry.SOURCE_BANK
        m=json.loads((parent/'manifest.json').read_text());library=(parent/source.VARIANT/'bank.spice').read_text()
        out=p.ROOT/'build/unused-matched-entry-test';rows=list(p.tasks(out,m,library))
        self.assertEqual(len(rows),4)
        self.assertEqual([r[0]['centered'] for r in rows],[True,True,False,False])
        for a,b in ((0,2),(1,3)):
            self.assertEqual(rows[a][1].replace(source.numerical_trial.CARD+'\n',''),rows[b][1])
            self.assertEqual(rows[a][2],rows[b][2])
        for task,text,obs in rows:
            before,original_obs=p.entry.fixture(out,m['identity'],library,dict(task['spec'],input_slew_ps=250),task['centered'])
            self.assertEqual(text.replace(p.waveform.source(task['spec']),p.entry.waveform.source(dict(task['spec'],input_slew_ps=250))),before)
            self.assertEqual(obs,original_obs);self.assertEqual(sum(len(o['devices']) for o in obs.values()),4112)
