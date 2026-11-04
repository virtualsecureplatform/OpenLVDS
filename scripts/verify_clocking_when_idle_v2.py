#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run a proof consumer after the producer releases its execution lock.

After= a Type=simple service orders startup, not process completion. Existing
consumers deliberately take the producer's exact flock non-blockingly. Retry
only that lock-contention exception; terminal-state, witness and measurement
failures remain failures. No producer is restarted or modified.
"""
import argparse
import errno
from pathlib import Path
import time


def consumer(artifact):
    namespace=artifact.parent.name
    if namespace=='analog_arbiter_pvt_v2':
        from verify_analog_arbiter_pvt_v2 import verify
    elif namespace=='dcdl_control_margin_v2':
        from verify_dcdl_control_margin_v2 import verify
    elif namespace=='dcc_clock_hold_pvt_v2':
        from verify_dcc_clock_hold_pvt_v2 import verify
    else:raise ValueError('Unsupported clocking proof context')
    return verify


def verify_when_idle(artifact,verify=None,pause=time.sleep):
    verify=verify or consumer(artifact)
    while True:
        try:return verify(artifact)
        except BlockingIOError as error:
            if error.errno not in (errno.EAGAIN,errno.EWOULDBLOCK):raise
            pause(1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify_when_idle(a.artifact.resolve()),flush=True)
