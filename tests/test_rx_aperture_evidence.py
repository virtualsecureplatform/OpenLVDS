# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import rx_aperture_evidence as evidence


class ApertureEvidence(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.artifact = self.root/'build/characterization/rx_aperture/fixture'
        self.artifact.mkdir(parents=True)
        requirements = (evidence.ROOT/'requirements.json').read_bytes()
        (self.root/'requirements.json').write_bytes(requirements)
        (self.artifact/'requirements.json').write_bytes(requirements)
        (self.artifact/'library.spice').write_text('native full-RC capture model')
        identity = dict(model=dict(netlist_sha256='current circuit'), code={}, simulator_provenance='fixture',
                        requirements_sha256=evidence.sha(self.root/'requirements.json'),
                        library_sha256=evidence.sha(self.artifact/'library.spice'))
        (self.artifact/'manifest.json').write_text(json.dumps(dict(identity=identity)))
        self.table = dict(passed=True, conditions=480, clock_mhz=410, load_ff=20, guard_ps=20,
                          resolution_ps=5, additional_link_margin_ps=200, model_sha256='current circuit',
                          manifest_sha256=evidence.sha(self.artifact/'manifest.json'),
                          simulator_provenance='fixture', producer_code={}, results=[], bounds={})
        for target, value in [('ROOT',self.root), ('provenance',lambda:'fixture')]:
            p = patch.object(evidence,target,value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(evidence.capture,'code_hashes',return_value={})
        p.start()
        self.addCleanup(p.stop)

    def read(self, model='current circuit'):
        path = self.artifact/'table.json'
        path.write_text(json.dumps(self.table))
        return evidence.read_table(path,model,'tt',25)

    def test_pass_flag_cannot_replace_the_measured_matrix(self):
        with self.assertRaisesRegex(ValueError,'matrix'):
            self.read()

    def test_changed_circuit_or_producer_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'stale'):
            self.read('another circuit')
        self.table['producer_code'] = {'producer.py':'edited'}
        with self.assertRaisesRegex(ValueError,'stale'):
            self.read()


if __name__ == '__main__':
    unittest.main()
