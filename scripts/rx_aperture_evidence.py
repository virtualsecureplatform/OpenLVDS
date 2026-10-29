# SPDX-License-Identifier: GPL-3.0-only
"""Read a complete, current full-RC capture aperture table for link timing."""
import hashlib
import json
from pathlib import Path
import re

import characterize_rx_aperture as capture
from dll_measurements import read_wave
from spice_engine import provenance

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_witness(root, manifest, spec, distance, expected):
    point = root/capture.condition_id(spec)/('point_'+f'{distance:.6f}'.replace('-', 'm').replace('.', 'p'))
    record = json.loads((point/'summary.json').read_text())
    if (record['spec'] != spec or record['distance_ps'] != distance or
            record['deck_sha256'] != sha(point/'bench.cir') or
            record['waveform_sha256'] != sha(point/'bench.cir.prn')):
        raise ValueError('Capture aperture witness changed')
    deck = (point/'bench.cir').read_text()
    body, timing = capture.fixture(spec, distance, manifest['identity']['model']['ports'])
    if body not in deck:
        raise ValueError('Capture aperture witness stimulus changed')
    for expression in [r'(?m)^VD VDDD 0 1\.8$', r'(?m)^\.options device temp='+str(spec['temperature'])+'$',
                       r'(?m)^\.lib "[^"\n]*'+re.escape(json.loads((root/'requirements.json').read_text())['pdk_version'])+r'[^"\n]*sky130\.lib\.spice" '+spec['process']+'$']:
        if len(re.findall(expression, deck)) != 1:
            raise ValueError('Capture aperture PVT or supply changed')
    wave, header = read_wave(point/'bench.cir.prn')
    measured = capture.measure(wave, header, spec, timing, distance)
    if measured != record['measurement'] or measured.get('passed') is not expected or 'error' in measured:
        raise ValueError('Capture aperture witness no longer measures the claimed result')


def read_table(path, model_sha256, process, temperature):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT/'build/characterization/rx_aperture'):
        raise ValueError('Capture aperture table is outside its artifact directory')
    root = path.parent
    table = json.loads(path.read_text())
    manifest = json.loads((root/'manifest.json').read_text())
    identity = manifest['identity']
    requirements = json.loads((ROOT/'requirements.json').read_text())
    if not (table.get('passed') and table.get('conditions') == 480 and
            table.get('clock_mhz') == 410 and table.get('load_ff') == 20 and
            table.get('guard_ps') == 20 and table.get('resolution_ps') == 5 and
            table.get('additional_link_margin_ps') == requirements['minimum_sampling_margin_ps'] and
            table.get('model_sha256') == model_sha256 == identity['model']['netlist_sha256'] and
            table.get('manifest_sha256') == sha(root/'manifest.json') and
            identity['requirements_sha256'] == sha(ROOT/'requirements.json') == sha(root/'requirements.json') and
            identity['library_sha256'] == sha(root/'library.spice') and
            table.get('simulator_provenance') == provenance() == identity['simulator_provenance'] and
            table.get('producer_code') == identity['code'] == capture.code_hashes()):
        raise ValueError('Missing, stale, or incomplete capture aperture qualification')
    for name, value in identity['code'].items():
        if sha(root/name) != value:
            raise ValueError('Captured aperture producer changed')
    expected = {capture.condition_id(spec):spec for spec in capture.conditions(requirements)}
    actual = {capture.condition_id(result['spec']):result for result in table['results']}
    if set(actual) != set(expected) or len(table['results']) != len(expected):
        raise ValueError('Capture aperture matrix is incomplete')
    bounds = {}
    for name, spec in expected.items():
        result = actual[name]
        if not (result.get('passed') and result['spec'] == spec and result['guard_ps'] == 20 and
                0 < result['passed_ps']-result['failed_ps'] <= 5 and
                result['bound_ps'] == capture.guarded_bound(result['passed_ps'])):
            raise ValueError('Invalid capture aperture boundary')
        # The failing bracket, passing bracket, and guarded passing witness
        # establish the bound independently of the summary's pass flag.
        for distance, passed in [(result['failed_ps'], False), (result['passed_ps'], True), (result['bound_ps'], True)]:
            verify_witness(root, manifest, spec, distance, passed)
        corner = f'{spec["process"]}_{spec["temperature"]}'
        bound = bounds.setdefault(corner, dict(setup_ps=0, hold_ps=0))
        key = spec['kind']+'_ps'
        bound[key] = max(bound[key], result['bound_ps'])
    if bounds != table['bounds']:
        raise ValueError('Capture aperture corner bounds differ from measured boundaries')
    selected = bounds[f'{process}_{temperature}']
    return dict(qualified=True, table=str(path.relative_to(ROOT)), table_sha256=sha(path),
                model_sha256=model_sha256, **selected, guard_ps=20, resolution_ps=5,
                input_slew_ps=[20,200],consumer_sha256=sha(Path(__file__)))


def load(model_sha256, process, temperature, path=None):
    if path is not None:
        return read_table(path, model_sha256, process, temperature)
    base = ROOT/'build/characterization/rx_aperture'
    for candidate in sorted(base.glob('*/table.json'), key=lambda p:p.stat().st_mtime, reverse=True):
        try:
            return read_table(candidate, model_sha256, process, temperature)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    raise ValueError('No current full-RC receiver aperture table; run scripts/characterize_rx_aperture.py')


def matches(record, process, temperature):
    try:
        info = json.loads((ROOT/'build/extracted/digital.json').read_text())['designs']['openlvds_ddr_rx']
        from spice_library import digital_current, checked_netlist
        digital_current('openlvds_ddr_rx', info)
        checked_netlist(info)
        return read_table(ROOT/record['table'], info['netlist_sha256'], process, temperature) == record
    except (OSError, ValueError, KeyError, TypeError):
        return False
