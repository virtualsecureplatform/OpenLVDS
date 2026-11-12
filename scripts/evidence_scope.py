# SPDX-License-Identifier: GPL-3.0-only
"""Reuse measured evidence only when its entire active circuit is unchanged."""
import hashlib
from spice_scope import closure_hash

TOPS=dict(driver='openlvds_driver',receiver='openlvds_receiver',dll='openlvds_dll',delay='openlvds_delay_line',
    link=('openlvds_driver','openlvds_receiver'))

# Contract benches instantiate the released macros, so extraction of a macro
# must change the scope even though the legacy wrappers below it are unchanged.
IO_TOPS=dict(driver='openlvds_io_tx',receiver='openlvds_io_rx',link=('openlvds_io_tx','openlvds_io_rx'))

def scope_hash(data,test,released=False):
    """Closure hash of one top, or of every top a multi-macro bench instantiates."""
    tops=(IO_TOPS if released else TOPS)[test]
    if isinstance(tops,str):return closure_hash(data,tops)
    return hashlib.sha256(''.join(closure_hash(data,top) for top in tops).encode()).hexdigest()

def matches(evidence,snapshot,expected,test,released=False):
    if expected is None or not snapshot.exists():return False
    data=snapshot.read_bytes()
    if hashlib.sha256(data).hexdigest()!=evidence.get('source_sha256'):return False
    try:return scope_hash(data,test,released)==scope_hash(expected,test,released)
    except (ValueError,KeyError):return False
