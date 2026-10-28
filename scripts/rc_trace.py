# SPDX-License-Identifier: GPL-3.0-only
"""Evidence for one completed RC reference transient, independent of its analysis."""
import hashlib
import json
from spice_scope import closure_hash


def digest(data):return hashlib.sha256(data).hexdigest()


def record(folder,top,scope,inputs,simulator,provenance,requirements):
    result=dict(completed=True,top=top,scope_sha256=scope,inputs=inputs,
        simulator=simulator,simulator_provenance=provenance,requirements_sha256=requirements,
        files={name:digest((folder/name).read_bytes()) for name in
            ['library.spice','bench.cir','bench.cir.prn','producer.py']})
    (folder/'trace_evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def verified(folder,simulator,provenance,requirements,record_sha256=None):
    try:
        data=(folder/'trace_evidence.json').read_bytes()
        if record_sha256 is not None and digest(data)!=record_sha256:return None
        evidence=json.loads(data)
        if not (evidence.get('completed') and evidence.get('simulator')==simulator and
                evidence.get('simulator_provenance')==provenance and evidence.get('requirements_sha256')==requirements):return None
        if set(evidence.get('files',{}))!={'library.spice','bench.cir','bench.cir.prn','producer.py'}:return None
        if any(digest((folder/name).read_bytes())!=stamp for name,stamp in evidence['files'].items()):return None
        if closure_hash((folder/'library.spice').read_bytes(),evidence['top'])!=evidence['scope_sha256']:return None
        return evidence
    except (OSError,ValueError,KeyError,TypeError):return None


def matching(folder,deck,scope,inputs,simulator,provenance,requirements):
    evidence=verified(folder,simulator,provenance,requirements)
    if not evidence:return False
    return (evidence['scope_sha256']==scope and evidence['inputs']==inputs and
            evidence['files']['bench.cir']==digest(deck.encode()))
