# SPDX-License-Identifier: GPL-3.0-only
"""Shared fail-closed qualification contract for approximate RC consumers."""
import hashlib
from pathlib import Path
from spice_engine import engine,provenance

REQUIRED={'driver','receiver','dll','delay','tx','rx'}

def valid(certificate,inputs,subset=False):
    cases=certificate.get('cases',{})
    runner=Path(__file__).with_name('validate_fast.py')
    if not (certificate.get('passed') and certificate.get('complete_suite') and
            set(cases)==REQUIRED and all(v.get('passed') for v in cases.values()) and
            certificate.get('runner_sha256')==hashlib.sha256(runner.read_bytes()).hexdigest() and
            certificate.get('simulator')==engine() and certificate.get('simulator_provenance')==provenance()):return False
    expected=certificate.get('fast_inputs',{})
    return all(expected.get(k)==v for k,v in inputs.items()) if subset else expected==inputs
