# SPDX-License-Identifier: GPL-3.0-only
"""Reuse measured evidence only when its entire active circuit is unchanged."""
import hashlib
from spice_scope import closure_hash

TOPS=dict(driver='openlvds_driver',receiver='openlvds_receiver',dll='openlvds_dll',delay='openlvds_delay_line')

def matches(evidence,snapshot,expected,test):
    if expected is None or not snapshot.exists():return False
    data=snapshot.read_bytes()
    if hashlib.sha256(data).hexdigest()!=evidence.get('source_sha256'):return False
    try:return closure_hash(data,TOPS[test])==closure_hash(expected,TOPS[test])
    except (ValueError,KeyError):return False
