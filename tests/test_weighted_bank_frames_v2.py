# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import normalize_weighted_bank_frames_v3 as frames


class PlacedFrameEquivalenceTests(unittest.TestCase):
    def checked(self,change=None,returncode=0):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);places={f'g{i}':dict(location=[10*i,0],orientation='N') for i in range(78)}
            old=dict(cell=dict(lef=['original.lef'],instances=places))
            new=dict(cell=dict(lef=['normalized.lef'],instances=places))
            ports=[f'g{i}\tcell\tA\tINPUT\tSIGNAL\tmet4\t{10*i}\t0\t{10*i+2}\t2' for i in range(78)]
            boxes=[f'g{i}\t{10*i}\t0\t{10*i+5}\t5' for i in range(78)]
            for tag in ['original','normalized']:
                (out/(tag+'_ports.tsv')).write_text('\n'.join(ports)+'\n')
                (out/(tag+'_boxes.tsv')).write_text('\n'.join(boxes)+'\n')
            if change=='pin':
                data=(out/'normalized_ports.tsv').read_text().replace('met4\t0\t0\t2\t2','met4\t1\t0\t2\t2')
                (out/'normalized_ports.tsv').write_text(data)
            if change=='duplicate':
                with (out/'normalized_ports.tsv').open('a') as f:f.write(ports[0]+'\n')
            if change=='box':
                data=(out/'normalized_boxes.tsv').read_text().replace('g0\t0\t0\t5\t5','g0\t1\t0\t5\t5')
                (out/'normalized_boxes.tsv').write_text(data)
            with patch.dict(os.environ,PDK_ROOT='/pdk'),patch.object(frames.previous.subprocess,'run',return_value=SimpleNamespace(returncode=returncode)):
                return frames.verify_ports(out,old,new,places)

    def test_exact_ports_boxes_and_all_78_macro_instances_are_required(self):
        result=self.checked()
        self.assertTrue(result['passed']);self.assertEqual(result['placed_macros'],78)
        self.assertEqual(result['placed_port_rectangles'],78)
        for change in ['pin','duplicate','box']:
            self.assertFalse(self.checked(change=change)['passed'])

    def test_tool_failure_cannot_pass_even_with_identical_saved_rectangles(self):
        self.assertFalse(self.checked(returncode=1)['passed'])
