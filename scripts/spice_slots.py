# SPDX-License-Identifier: GPL-3.0-only
"""Host-wide project SPICE slots (six unless OPENLVDS_SPICE_SLOTS says otherwise), with a reservation for the frozen RX job."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]


def total_slots():
    """Six by default. A host with spare cores and memory may raise it for one session."""
    value=int(os.environ.get('OPENLVDS_SPICE_SLOTS','6'))
    if not 1<=value<=64:raise ValueError('OPENLVDS_SPICE_SLOTS must be between 1 and 64')
    return value


def reserved_slots(root=ROOT):
    state=root/'build/characterization/rx_aperture/e9ca7d2f2ae6d61b/state.json'
    if state.exists() and json.loads(state.read_text()).get('status')!='complete':
        return 4
    return 0


@contextmanager
def slot(root=ROOT):
    directory=root/'build/diagnostics/spice_slots';directory.mkdir(parents=True,exist_ok=True)
    handle=None
    try:
        while handle is None:
            for index in range(reserved_slots(root),total_slots()):
                candidate=(directory/str(index)).open('a')
                try:
                    fcntl.flock(candidate,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    handle=candidate
                    break
                except BlockingIOError:
                    candidate.close()
            if handle is None:time.sleep(.25)
        yield
    finally:
        if handle is not None:handle.close()
