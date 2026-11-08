# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import four_bank_fixture_300_v2 as p
import four_bank_native_measure_300_v1 as reader
import next_bank_tg2_materials_300_v1 as source
from run_native_binary_v2 import translate


class RequiredObservationTests(unittest.TestCase):
    def test_actual_writer_covers_real_reader_requirements(self):
        m=json.loads((source.PARENT/'manifest.json').read_text());i=m['identity'];variant=source.producer.VARIANT
        identity=dict(i['source_identity'],observations=i['observations'][variant])
        library=(source.PARENT/variant/'bank.spice').read_text();original=(source.PARENT/'0/bench.cir').read_text()
        args=(original,library,i['revisions'][variant]['macro_top'],identity)
        old,old_obs=p.previous.fixture(*args);new,obs=p.fixture(*args)
        self.assertEqual(obs,old_obs)
        self.assertEqual([l for l in old.splitlines() if not l.startswith('.print tran ')],
                         [l for l in new.splitlines() if not l.startswith('.print tran ')])
        _,saved=translate(new);_,old_saved=translate(old)
        requested=set()
        def collect(path,names,stop):
            requested.update(names)
            raise RuntimeError('captured reader request without opening a trace')
        with patch.object(reader,'validate',side_effect=collect):
            with self.assertRaisesRegex(RuntimeError,'captured reader request'):
                reader.measure(Path('unused'),obs,m['tasks'][0]['spec'])
        self.assertTrue(requested<=set(saved),sorted(requested-set(saved)))
        self.assertEqual(requested-set(old_saved),{'v(b1_out)','v(b2_out)','v(b3_out)'})
        self.assertEqual(set(saved)-set(old_saved),{'v(b1_out)','v(b2_out)','v(b3_out)'})
