# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from continue_receiver_candidate import admitted,selected


class ReceiverContinuation(unittest.TestCase):
    def summary(self):
        return dict(diagnostic_complete=True,results=[dict(task=name,receiver_transport=dict(
            missing_output_edges=0,pulses=[dict(output_edges_in_next_input_period=1)]))
            for name in ['captured','sharp_control']])

    def test_both_complete_unique_native_cases_are_required(self):
        good=self.summary();admitted(good)
        good['results'][1]['task']='captured'
        with self.assertRaisesRegex(ValueError,'Incomplete'):admitted(good)
        with self.assertRaisesRegex(ValueError,'Incomplete'):admitted(dict(diagnostic_complete=False,results=[]))

    def test_missing_extra_or_absent_edges_stop_followup(self):
        for count in [0,2]:
            case=self.summary();case['results'][0]['receiver_transport']['pulses'][0]['output_edges_in_next_input_period']=count
            with self.assertRaisesRegex(ValueError,'clock edges'):admitted(case)
        case=self.summary();case['results'][0]['receiver_transport']['missing_output_edges']=1
        with self.assertRaisesRegex(ValueError,'clock edges'):admitted(case)

    def test_component_and_link_selection_must_match_native_receiver(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths=[root/name for name in ['replay','components','link']]
            values=[dict(layout='selected',code={}),dict(layout='selected',replay='replay',code={}),
                    dict(receiver='selected',replay='replay',code={})]
            for path,value in zip(paths,values):
                path.mkdir();(path/'manifest.json').write_text(json.dumps(dict(identity=value)))
            selected(*paths,root=root)
            values[2]['receiver']='another'
            (paths[2]/'manifest.json').write_text(json.dumps(dict(identity=values[2])))
            with self.assertRaisesRegex(ValueError,'different receiver'):selected(*paths,root=root)
