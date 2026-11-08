#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exact terminal-reader comparison on one closed native trace; no SPICE run."""
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import native_terminal_blocks_300_v1 as blocks
import probe_tg2_p40n32_300 as source
from native_binary_raw_v2 import validate

ROOT=source.ROOT
PARENT=ROOT/'build/diagnostics/tg2_p40n32_pilot_300_v1/aae4b31d0e77445c'
VERSION='completed-native-all-terminal-block-reader-benchmark-300-v1'


def run():
    m=source.bound(PARENT,full=False);i=m['identity'];folder=PARENT/'0'
    row=json.loads((folder/'summary.json').read_text())
    if row['task']!=m['tasks'][0] or row['error'] is not None:
        raise ValueError('Require completed unchanged native zero-code point')
    for n,h in row['files'].items():
        if source.sha(folder/n)!=h:raise ValueError('Completed native point changed')
    devices=i['observations'][source.VARIANT]['devices']
    column=lambda n:'v('+n.lower().replace(':','.')+')'
    names,w=validate(folder/'bench.raw',{column(n) for d in devices for n in d['terminals'] if n!='0'},40e-9)
    if w[0,names.index('time')]!=0:raise ValueError('Require actual native DC/startup sample')
    paths=[PARENT/'manifest.json',folder/'summary.json',*[folder/n for n in row['files']]]
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**i['guards'],**{str(p.relative_to(ROOT)):source.sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),case='0',inputs=inputs,
        block_rows=256,ancestral_native_raw_rehashed=False,
        scope='One completed waveform reader equivalence and case-specific timing; no solver, model, bank or PHY qualification')
    out=ROOT/'build/diagnostics/native_terminal_block_benchmark_300_v1'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    source.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    source.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        lookup={n:k for k,n in enumerate(names)};ground=np.zeros(len(w));baseline=[]
        start=time.perf_counter()
        for d in devices:
            v=[ground if n=='0' else w[:,lookup[column(n)]] for n in d['terminals']]
            peak=float(np.max(np.maximum.reduce(v)-np.minimum.reduce(v)))
            baseline.append(dict(device=d['name'],maximum_terminal_difference_v=peak,limit_v=d['limit_v'],passed=bool(peak<=d['limit_v'])))
        reference_seconds=time.perf_counter()-start;start=time.perf_counter()
        actual=blocks.envelopes(names,w,devices,block_rows=256)
        block_seconds=time.perf_counter()-start
        if baseline!=actual or actual!=row['result']['terminal_stress']:
            raise ValueError('Block reader failed exact original all-device stress reproduction')
        if any(source.sha(ROOT/n)!=h for n,h in inputs.items()):
            raise ValueError('Native reader benchmark inputs changed')
        source.atomic(out/'summary.json',dict(exact_original_terminal_metrics_reproduced=True,
            native_mos=len(devices),native_samples=len(w),all_startup_samples_retained=True,
            reference_per_device_seconds=reference_seconds,block_seconds=block_seconds,
            recorded_reference_over_block_ratio=reference_seconds/block_seconds,
            reference_ran_first=True,block_scan_after_reference_cache_warmup=True,
            standardized_performance_benchmark=False,production_reader_replaced=False,
            solver_or_model_modified=False,qualified_phy=False,scope=identity['scope']))
        source.atomic(out/'state.json',dict(status='complete',passed=True,qualified_phy=False))
    except Exception as exc:
        source.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':print(run(),flush=True)
