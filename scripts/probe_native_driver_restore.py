#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare audited native driver restoration variants in the original loaded link fixture."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from driver_restore_variant import source_variant, TOP
from layout_driver_restore_candidate import PORTS
from dll_candidate_library import audited
from spice_library import checked_netlist
from probe_driver_internal import aliases
from dll_campaign import atomic
from dll_measurements import read_wave
from probe_driver_internal import instrument as observation_instrument
from reduce_rc import number
from simulate_link import analyze, edge_times, word_stream, REQ
from spice_engine import command, engine, provenance
from spice_probes import ProbeNetwork
from spice_scope import closure_hash
from spice_slots import slot
from stage_phy_candidate import overlay

ROOT = Path(__file__).resolve().parents[1]
CODE = ['probe_native_driver_restore.py','layout_driver_restore_candidate.py','driver_restore_candidate_rc.py', 'extract.py','audit_rc.py','lvs_utils.py','spice_library.py','dll_candidate_library.py', 'driver_restore_variant.py', 'dll_campaign.py', 'dll_measurements.py',
        'probe_driver_internal.py', 'reduce_rc.py', 'simulate_link.py', 'spice_engine.py', 'spice_probes.py',
        'spice_scope.py', 'spice_slots.py', 'stage_phy_candidate.py', 'run_ngspice.py', 'layout.py']
PROTECTED = ('openlvds_receiver_core', 'lvds_bias', 'openlvds_dll', 'openlvds_delay_line',
             'openlvds_tx_core', 'openlvds_ddr_rx')
CASES = ['source_control', 'restore_64_24']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(parent_deck, parent, folder, library):
    probes = aliases(library)
    deck = observation_instrument(parent_deck, parent, folder, probes)
    matches = list(re.finditer(r'(?im)^\.tran[^\n]*$', deck))
    if len(matches)!=1:
        raise ValueError('Expected one original transient command')
    row=matches[0];fields=row[0].split()
    if (len(fields)!=5 or number(fields[1])!=20e-12 or number(fields[3])!=0 or
            number(fields[4])!=100e-12):
        raise ValueError('Expected original 20 ps output and 100 ps maximum integration step')
    strict=re.sub(r'\S+(\s*)$',r'20p\1',row[0])
    return deck[:row.start()]+strict+deck[row.end():],probes


def physical_models(layouts):
    if set(layouts)!=set(CASES):raise ValueError('Both matched native driver variants are required')
    source=(ROOT/'analog/openlvds.spice').read_text();models={};files=[];code=set()
    for case,folder in layouts.items():
        if not folder.is_relative_to(ROOT/'build/diagnostics/driver_layout'):
            raise ValueError('Use isolated matched driver layouts')
        summary=json.loads((folder/'summary.json').read_text())
        info=json.loads((folder/'extraction.json').read_text())
        expected=source_variant(source,case=='restore_64_24')
        if (not summary['passed'] or summary['identity']['variant']!=case or
                (folder/'candidate.spice').read_text()!=expected or
                summary['source_sha256']!=digest(folder/'candidate.spice')):
            raise ValueError('Native driver layout differs from its declared variant')
        if info['ports']!=PORTS:raise ValueError('Native driver port order changed')
        for name,stamp in summary['files'].items():
            if digest(folder/name)!=stamp:raise ValueError('Original driver physical evidence changed')
        for name,stamp in summary['identity']['code'].items():
            if digest(ROOT/'scripts'/name)!=stamp:raise ValueError('Driver physical producer changed')
        gds=ROOT/summary['designs'][TOP]['gds']
        if digest(gds)!=info['gds_sha256'] or info['source_sha256']!=summary['source_sha256']:
            raise ValueError('Driver GDS/extraction binding changed')
        audit=audited(folder,info);models[case]=checked_netlist(info)
        files += [folder/name for name in ['summary.json','candidate.spice','extraction.json','rc_audit.json']]
        files += [folder/name for name in summary['files']]+[ROOT/info['netlist'],ROOT/audit['report']]
        code.update(summary['identity']['code'])
    return models,files,code


def prepare(parent,control,candidate):
    if engine() != 'ngspice' or not parent.is_relative_to(ROOT / 'build/diagnostics/receiver_candidate_link'):
        raise ValueError('Use the completed saved native receiver link')
    layouts={'source_control':control,'restore_64_24':candidate}
    models,physical_files,physical_code=physical_models(layouts)
    capture = json.loads((parent / 'manifest.json').read_text())
    context = capture['identity']
    report = json.loads((parent / 'summary.json').read_text())
    for name, stamp in context['inputs'].items():
        if digest(ROOT / name) != stamp:
            raise ValueError('Parent link input changed')
    for name, stamp in context['code'].items():
        if digest(ROOT / 'scripts' / name) != stamp:
            raise ValueError('Parent link producer changed')
    if provenance() != context['simulator_provenance']:
        raise ValueError('Parent link runtime changed')
    for name, stamp in [('manifest.json', report['manifest_sha256']), ('bench.cir', report['deck_sha256']),
                        ('bench.cir.prn', report['waveform_sha256']), ('library.spice', capture['library_sha256'])]:
        if digest(parent / name) != stamp:
            raise ValueError('Parent link evidence changed')
    paths = [parent / n for n in ['manifest.json', 'summary.json', 'bench.cir', 'bench.cir.prn', 'library.spice']]
    paths += [ROOT / 'analog/openlvds.spice', ROOT / 'requirements.json']+physical_files
    identity = dict(parent=str(parent.relative_to(ROOT)), parent_config=context['parent_config'],
        simulator_provenance=provenance(), native_driver_only=True, maximum_step_ps=20, parallel_jobs=2,
        layouts={case:str(path.relative_to(ROOT)) for case,path in layouts.items()},
        inputs={str(p.relative_to(ROOT)): digest(p) for p in paths},
        code={n: digest(ROOT / 'scripts' / n) for n in sorted(set(CODE) | set(context['code']) | physical_code)})
    root = ROOT / 'build/diagnostics/driver_native_restore' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if (root / 'manifest.json').exists():
        return root
    root.mkdir(parents=True)
    baseline = (parent / 'library.spice').read_text()
    tasks = []
    parent_deck = (parent / 'bench.cir').read_text()
    stop = re.search(r'(?im)^\.tran\s+\S+\s+(\S+)', parent_deck)
    if not stop:
        raise ValueError('Missing original transient endpoint')
    for name in CASES:
        folder = root / name
        folder.mkdir()
        selected = models[name]
        library = overlay(baseline, selected, TOP, PROTECTED)
        if closure_hash(library, TOP) != closure_hash(selected, TOP):
            raise ValueError('Selected native driver differs from its declared variant')
        deck, probes = fixture(parent_deck, parent, folder, library)
        # Native driver nodesets retain their original named buses.
        internal = re.findall(r'(?i)V\((X(?:CT|DT):[^)]+)\)', deck)
        ProbeNetwork(library).validate(deck, internal)
        (folder / 'library.spice').write_text(library)
        (folder / 'bench.cir').write_text(deck)
        tasks.append(dict(id=name, native_driver_only=True, stop_seconds=number(stop[1]), observation_nodes=probes,
            files={n: digest(folder / n) for n in ['library.spice', 'bench.cir']}))
    atomic(root / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT / 'build/diagnostics/driver_native_restore'):
        raise ValueError('Use a prepared matched native driver experiment')
    manifest = json.loads((root / 'manifest.json').read_text())
    identity = manifest['identity']
    if identity['maximum_step_ps'] != 20 or identity['parallel_jobs'] != 2 or [t['id'] for t in manifest['tasks']] != CASES:
        raise ValueError('Both source driver controls are required exactly once')

    def unchanged():
        if provenance() != identity['simulator_provenance']:
            raise ValueError('Driver restoration runtime changed')
        for name, stamp in identity['inputs'].items():
            if digest(ROOT / name) != stamp:
                raise ValueError('Driver restoration input changed')
        for name, stamp in identity['code'].items():
            if digest(ROOT / 'scripts' / name) != stamp:
                raise ValueError('Driver restoration producer changed')
        parent = ROOT / identity['parent']
        baseline = (parent / 'library.spice').read_text()
        models,_,_=physical_models({case:ROOT/path for case,path in identity['layouts'].items()})
        for task in manifest['tasks']:
            folder = root / task['id']
            if any(digest(folder / n) != h for n, h in task['files'].items()):
                raise ValueError('Driver restoration fixture changed')
            expected = overlay(baseline, models[task['id']], TOP, PROTECTED)
            deck, _ = fixture((parent / 'bench.cir').read_text(), parent, folder, expected)
            if (folder / 'library.spice').read_text() != expected or (folder / 'bench.cir').read_text() != deck:
                raise ValueError('Driver restoration changes more than the declared native driver')

    with (root / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        def execute(task):
            folder = root / task['id']
            cached = json.loads((folder / 'summary.json').read_text()) if (folder / 'summary.json').exists() else None
            if cached is None:
                atomic(folder / 'execution.json', dict(status='waiting_for_slot', qualified_phy=False))
                with slot():
                    unchanged()
                    atomic(folder / 'execution.json', dict(status='running', qualified_phy=False))
                    process = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                                             cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(process.stdout + process.stderr)
                process.check_returncode()
            unchanged()
            wave, headers = read_wave(folder / 'bench.cir.prn')
            t = wave[:, 1]
            if len(t)<2 or not np.isfinite(wave).all() or np.any(np.diff(t) <= 0) or t[0]>1e-15 or t[-1] < task['stop_seconds'] - 1e-12:
                raise ValueError('Incomplete driver restoration trace')
            config = identity['parent_config']
            rises = edge_times(t, wave[:, headers['V(CLK0)']], .9, True)
            launch = rises[rises >= config['training_ns'] * 1e-9][:config['bits'] // 2] * 1e9
            if len(launch) != config['bits'] // 2:
                raise ValueError('Incomplete original payload launch sequence')
            decoded = analyze(wave, word_stream(len(launch)), launch, 1000 / config['mhz'])
            decoded['sampling_margin_passed'] = all(decoded.get(k) is not None and
                decoded[k] >= REQ['minimum_sampling_margin_ps'] for k in ['setup_margin_ps', 'hold_margin_ps'])
            decoded['passed'] = decoded['passed'] and decoded['sampling_margin_passed']
            eyes = {}
            for lane, p, n in [('tx_clock', 'CP', 'CN'), ('rx_clock', 'RCP', 'RCN')]:
                values = wave[:, headers['V(' + p + ')']] - wave[:, headers['V(' + n + ')']]
                crossings = edge_times(t, values, 0)
                centers = (crossings[:-1] + crossings[1:]) / 2
                centers = centers[(centers >= 60e-9) & (centers <= 120e-9)]
                magnitude = abs(np.interp(centers, t, values))
                if not len(magnitude):
                    raise ValueError('No complete clock pulse centers')
                eyes[lane] = dict(min_center_abs_v=float(magnitude.min()),
                    below_rx_threshold=int(np.count_nonzero(magnitude < REQ['rx_threshold_v'])))
            observations={};keep=(t>=60e-9)&(t<=120e-9)
            for tag,node in task['observation_nodes'].items():
                values=wave[:,headers['V('+node.upper()+')']]
                level=.9 if tag.endswith(('__AD','__AB')) else 1.65
                crossings={}
                for polarity,rising in [('rising_ns',True),('falling_ns',False)]:
                    edges=edge_times(t,values,level,rising)
                    crossings[polarity]=(edges[(edges>=60e-9)&(edges<=120e-9)]*1e9).tolist()
                observations[tag]=dict(min_v=float(values[keep].min()),max_v=float(values[keep].max()),
                    crossing_level_v=level,**crossings)
            comparison={}
            if task['id']=='source_control':
                reference,reference_headers=read_wave(ROOT/identity['parent']/'bench.cir.prn')
                grid=np.linspace(60e-9,120e-9,5001)
                for name in ['V(TXCLOCK)','V(CP)','V(CN)','V(RCP)','V(RCN)']:
                    comparison[name]=float(np.max(abs(np.interp(grid,t,wave[:,headers[name]])-
                        np.interp(grid,reference[:,1],reference[:,reference_headers[name]]))))
            result = dict(task=task['id'], diagnostic_complete=True, qualified_phy=False, native_driver_only=True,
                maximum_step_ps=20,decoder=decoded, clock_centers=eyes,observation_nodes=observations,
                original_control_comparison_max_abs_v=comparison,manifest_sha256=digest(root / 'manifest.json'),
                waveform_sha256=digest(folder / 'bench.cir.prn'),
                scope='Matched audited native driver variants in the original loaded fixture; stricter 20 ps maximum integration step; no electrical or PHY qualification')
            if cached is not None and cached != result:
                raise ValueError('Driver restoration cached analysis differs from waveform')
            atomic(folder / 'summary.json', result)
            atomic(folder / 'execution.json', dict(status='completed', qualified_phy=False))
            return result
        def checked_execute(task):
            try:return execute(task)
            except Exception as error:
                atomic(root/task['id']/'execution.json',dict(status='held_for_diagnosis',qualified_phy=False,error=str(error)))
                raise
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(checked_execute, manifest['tasks']))
        unchanged()
        atomic(root / 'summary.json', dict(diagnostic_complete=True, qualified_phy=False,
            native_driver_only=True, manifest_sha256=digest(root / 'manifest.json'), results=results))
    print(root / 'summary.json', flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('artifact',type=Path)
    parser.add_argument('--control',type=Path)
    parser.add_argument('--candidate',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':
        if args.control is None or args.candidate is None:parser.error('Preparation requires both matched physical layouts')
        print(prepare(args.artifact.resolve(),args.control.resolve(),args.candidate.resolve()),flush=True)
    else:run(args.artifact.resolve())
