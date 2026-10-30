#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Start, stop, or inspect DLL jobs independently of the terminal session."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from resident_dll_jobs import snapshot

ROOT = Path(__file__).resolve().parents[1]
UNIT = 'openlvds-resident.service'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'status', 'stop'])
    args = parser.parse_args()
    if args.action == 'start':
        active = subprocess.run(['systemctl','--user','is-active','--quiet',UNIT]).returncode == 0
        if not active:
            loaded = subprocess.run(['systemctl','--user','show',UNIT,'--property=LoadState','--value'],capture_output=True,text=True).stdout.strip() == 'loaded'
            if loaded:
                subprocess.run(['systemctl','--user','start',UNIT],check=True)
            else:
                subprocess.run(['systemd-run','--user','--unit='+UNIT,'--property=Restart=on-failure',
                    '--property=RestartSec=10s','--property=Delegate=yes','--property=WorkingDirectory='+str(ROOT),
                    sys.executable,str(ROOT/'scripts/resident_dll_jobs.py'),'--jobs','6'],check=True)
    elif args.action == 'stop':
        subprocess.run(['systemctl','--user','stop',UNIT],check=True)
    statefile = ROOT/'build/diagnostics/dll_architecture/6d99d42cf3eb5d31/state.json'
    state = json.loads(statefile.read_text())
    health = snapshot(state,state.get('supervisor_pid'),time.time()-statefile.stat().st_mtime)
    counts = {}
    for record in state['tasks'].values():
        counts[record['status']] = counts.get(record['status'],0)+1
    service = subprocess.run(['systemctl','--user','show',UNIT,'--property=ActiveState,MainPID,ControlGroup'],capture_output=True,text=True)
    print(json.dumps(dict(architecture_health=health,recorded_counts=counts,
                         heartbeat_age_seconds=round(time.time()-statefile.stat().st_mtime,1),
                         service=service.stdout.strip().splitlines()),indent=2))


if __name__ == '__main__':
    main()
