#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Harden an isolated RX output-driver experiment without changing frozen flows."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from rx_buffered_policy import retained, policy_parameters

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)


def run(out,strength=4,publication4=False):
    if (strength,publication4) not in [(4,False),(8,True)]:raise ValueError('Use buf4 or buf8 with publication4')
    policy='public-data-buf8-publish4' if publication4 else 'public-data-buf4'
    parameters=policy_parameters(policy)
    source_name='openlvds_ddr_rx_buffer8_publish4.v' if publication4 else 'openlvds_ddr_rx_buffer4.v'
    blackboxes='rx_buffer8_publish4_blackboxes.v' if publication4 else 'rx_buffer4_blackboxes.v' 
    out=out.resolve()
    if not out.is_relative_to(ROOT/'build/diagnostics'):raise ValueError('Use an isolated RX artifact')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'config.json').exists():raise ValueError('Preserve existing physical results; choose a new directory')
        files=[ROOT/'rtl/openlvds_reset.v',ROOT/'rtl/experiments'/source_name,
            ROOT/'sky130/experiments'/blackboxes,ROOT/'constraints/rx.sdc']
        source=files[1]
        if not retained(source.read_text(),**parameters):raise ValueError('RX source violates buffered topology')
        archive=out/'inputs';archive.mkdir()
        for p in files:(archive/p.name).write_bytes(p.read_bytes())
        base=ROOT/'build/physical/rx/config.json';config=json.loads(base.read_text())
        config.update(VERILOG_FILES=[str(archive/p.name) for p in files[:2]],
            EXTRA_VERILOG_MODELS=[str(archive/files[2].name)],
            PNR_SDC_FILE=str(archive/'rx.sdc'),SIGNOFF_SDC_FILE=str(archive/'rx.sdc'),
            DESIGN_REPAIR_BUFFER_OUTPUT_PORTS=False)
        cfg=out/'config.json';atomic(cfg,config)
        captured={p.name:digest(archive/p.name) for p in files};captured['config.json']=digest(cfg)
        code={p.name:digest(p) for p in [Path(__file__),ROOT/'scripts/rx_buffered_policy.py',ROOT/'scripts/physical_policy.py']}
        producers=out/'producers';producers.mkdir()
        for name in code:(producers/name).write_bytes((ROOT/'scripts'/name).read_bytes())
        stamp=hashlib.sha256(json.dumps(captured,sort_keys=True).encode()).hexdigest();tag=f'rx-buffer{strength}-'+stamp[:12]
        atomic(out/'identity.json',dict(rx_policy=policy,inputs=captured,producer_code=code,base_config_sha256=digest(base),qualified_phy=False))
        cmd=[sys.executable,'-m','librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],
            '-p','sky130A','-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar','--run-tag',tag,str(cfg)]
        with (out/'flow.log').open('w') as log:result=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        folder=out/'runs'/tag;netlist=folder/'final/nl/openlvds_ddr_rx.nl.v'
        topology=netlist.exists() and retained(netlist.read_text(),**parameters)
        unchanged=all(digest(archive/n if n!='config.json' else cfg)==h for n,h in captured.items()) and all(digest(ROOT/'scripts'/n)==h for n,h in code.items())
        summary=dict(passed=result.returncode==0 and topology and unchanged,returncode=result.returncode,
            source_sha256=stamp,inputs_unchanged=unchanged,interface_verified=topology,rx_policy=policy,
            run=str(folder.relative_to(ROOT)),input_archive=str(archive.relative_to(ROOT)),producer_code=code,
            qualified_phy=False,metrics=json.loads((folder/'final/metrics.json').read_text()) if (folder/'final/metrics.json').exists() else {})
        atomic(out/'summary.json',summary);print(out/'summary.json',flush=True)
        return 0 if summary['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--strength',type=int,choices=[4,8],default=4);p.add_argument('--publication4',action='store_true');a=p.parse_args();raise SystemExit(run(a.artifact,a.strength,a.publication4))
