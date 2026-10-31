# SPDX-License-Identifier: GPL-3.0-only
"""Bind a link result to the required case and its current simulation inputs."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from simulate_link import clocks,pwl
from spice_engine import engine,provenance
from rx_aperture_evidence import matches as aperture_matches

ROOT=Path(__file__).resolve().parents[1]


def digest(data):return hashlib.sha256(data).hexdigest()


def aperture_valid(aperture,config):
    if not config.get('bundle'):
        return aperture_matches(aperture,config['process'],config['temperature'])
    from phy_candidate import load
    from rx_aperture_evidence import read_table
    _,_,models=load(ROOT/config['bundle'])
    model=models['openlvds_ddr_rx'];exact=model.get('exact_sha256',model['netlist_sha256'])
    if aperture.get('model_sha256')!=exact:return False
    return read_table(ROOT/aperture['table'],exact,config['process'],config['temperature'])==aperture


def matches(summary,case,requirements,library):
    try:
        if not summary.get('passed') or summary.get('diagnostic',True):
            return False,'Unpassed or diagnostic result'
        config=summary['config']
        aperture=summary.get('rx_aperture',{})
        if not (aperture.get('qualified') and config.get('rx_aperture')==aperture and
                aperture_valid(aperture,config)):
            return False,'Missing or stale full-RC receiver aperture qualification'
        if not summary.get('capture_aperture_slew_passed'):
            return False,'Capture input slew is outside the characterized aperture domain'
        expected=dict(process='tt',temperature=25,mhz=400,duty=.5,skew_ps=0,
            eye_shift_ps=0,clock_source='ideal',dll_phase=True,settled_start=True,
            jitter_pp_ps=requirements['injected_jitter_pp_ps'])
        expected.update({k:v for k,v in case['config'].items() if k!='bits'})
        if any(config.get(k)!=v for k,v in expected.items()):
            return False,'Recorded configuration differs from the required case'
        if (config.get('diagnostic',True) or config['bits']<case['config']['bits'] or
                summary.get('checked_bits',0)<config['bits'] or summary.get('word_errors')!=0 or
                not summary.get('electrical_passed')):
            return False,'Incomplete bit coverage or electrical checks'
        if not config['eye_shift_ps'] and not summary.get('sampling_margin_passed'):
            return False,'Sampling margin has not passed'
        fast=summary.get('network')=='TICER approximate RC'
        if summary.get('network') not in ['TICER approximate RC','full distributed RC'] or config.get('fast_rc')!=fast:
            return False,'Unknown or inconsistent circuit view'
        if summary.get('simulator')!=engine() or config.get('simulator')!=engine() or summary.get('simulator_provenance')!=provenance():
            return False,'Simulator provenance changed'
        output=(ROOT/summary['output']).resolve()
        if not output.is_relative_to((ROOT/'build/link').resolve()):
            return False,'Evidence is outside the link artifact directory'
        if json.loads((output/'rx_aperture.json').read_text())!=aperture:
            return False,'Captured receiver aperture evidence changed'
        runner=(ROOT/'scripts/simulate_link.py').read_bytes()
        req=(ROOT/'requirements.json').read_bytes()
        if config.get('bundle'):
            from phy_candidate import load
            bundle=ROOT/config['bundle'];selected,inputs,_=load(bundle,fast)
            if (selected!=library or inputs!=summary['inputs'] or
                config['bundle_manifest_sha256']!=digest((bundle/'manifest.json').read_bytes())):
                return False,'Staged PHY bundle changed'
            source=(bundle/'full.spice').read_bytes()
        else:source=(ROOT/'analog/openlvds.spice').read_bytes()
        for filename,data,key in [('runner.py',runner,'runner_sha256'),
                ('requirements.json',req,'requirements_sha256'),
                ('analog_source.spice',source,'source_sha256'),
                ('library.spice',library,'library_sha256')]:
            if summary.get(key)!=digest(data) or (output/filename).read_bytes()!=data:
                return False,filename+' changed'
        for filename,key in [('bench.cir','deck_sha256'),('bench.cir.prn','waveform_sha256')]:
            if summary.get(key)!=digest((output/filename).read_bytes()):
                return False,filename+' changed'
        period=1000/summary['actual_clock_mhz']
        training=summary['training_ns']
        if period<=0 or training+1e-9<256*period:
            return False,'PHY training is incomplete'
        total=training+50+(config['bits']/2+16)*period
        c0,c90,_,actual_period,scope=clocks(SimpleNamespace(**config),total)
        clock_bytes=(pwl(c0)+pwl(c90)).encode()
        if (abs(actual_period-period)>1e-9 or scope!=summary['clock_partition'] or
                digest(clock_bytes)!=summary['clock_waveform_sha256']):
            return False,'Clock waveform or DLL characterization changed'
        fingerprint=digest(library+req+json.dumps(config,sort_keys=True).encode()+
            runner+provenance().encode()+clock_bytes+scope.encode())
        if summary['fingerprint']!=fingerprint or output.name!=fingerprint[:12]:
            return False,'Simulation fingerprint changed'
        return True,''
    except (OSError,ValueError,KeyError,TypeError,ZeroDivisionError) as error:
        return False,'Missing or invalid link evidence: '+str(error)
