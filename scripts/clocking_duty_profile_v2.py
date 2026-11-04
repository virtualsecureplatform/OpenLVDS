# SPDX-License-Identifier: GPL-3.0-only
"""Apply the approved duty-only amendment without changing frozen descriptors."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'clocking_duty_v2_2.json'


def load():
    amendment=json.loads(PROFILE.read_text());base=ROOT/amendment['base_descriptor']
    if (amendment['schema']!='openlvds-clocking-duty-amendment-v2.2'
        or amendment['qualified_phy'] or amendment['status']!='development_unqualified'
        or base!=ROOT/'clocking_v2.json' or hashlib.sha256(base.read_bytes()).hexdigest()!=amendment['base_sha256']
        or amendment['timing_overrides']!={'rx_reference_duty_range':[.4,.6]}):
        raise ValueError('Clock duty amendment changed outside its approved scope')
    result=json.loads(base.read_text());result['timing'].update(amendment['timing_overrides']);return result
