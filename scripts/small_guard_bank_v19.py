# SPDX-License-Identifier: GPL-3.0-only
"""Replace the two diagnostic drivers with their actual extracted components."""
import tg_driver_experiment_v9 as reference
from build_compound_drivers_v3 import cell_definition
from spice_library import replace
import native_clock_components_v2 as native

BASE = reference.name('regular_quad')
OLD = reference.baseline.previous.INVERTER
BIG = 'openlvds_inv_8_regular_o4_v14'
SMALL = 'openlvds_inv_8_regular_o3_v17'
PROFILES = {'fine3': (BIG, SMALL), 'both3': (SMALL, SMALL)}


def name(profile):
    if profile not in PROFILES:
        raise ValueError('Unknown physical small-guard bank profile')
    return 'openlvds_dcdl_tg_c16_f32_guard_'+profile+'_v19'


def transform(cells, bank, components, profile):
    name(profile)
    if set(components) != {BIG, SMALL}:
        raise ValueError('Require both independently verified actual driver RC models')
    before = native.definitions(cells)
    if OLD not in before or before[OLD][0] != ['A', 'Y', 'VGND', 'VPWR']:
        raise ValueError('Original driver interface changed')
    for model, text in components.items():
        defs = native.definitions(text)
        if set(defs) != {model} or defs[model][0] != before[OLD][0]:
            raise ValueError('Actual extracted driver model or port order changed')
    if bank.count('.subckt '+BASE+' ') != 1 or bank.count('.ends '+BASE+'\n') != 1:
        raise ValueError('Require unchanged regular-quad bank')
    cells = replace(cells, OLD, '\n'.join(components[n].strip() for n in (BIG, SMALL)))
    after = native.definitions(cells)
    if set(after) != (set(before)-{OLD})|{BIG, SMALL} or any(after[m] != before[m] for m in before if m != OLD):
        raise ValueError('Driver substitution changed another native component')
    expected = dict(Xinput_inverse=PROFILES[profile][0], Xfine_driver=PROFILES[profile][1])
    replaced = set(); rows = []
    for line in bank.splitlines():
        words = line.split()
        if words and words[0] in expected:
            if words[0] in replaced or len(words) != 6 or words[-1] != OLD:
                raise ValueError('Original two-driver graph changed')
            replaced.add(words[0]); words[-1] = expected[words[0]]; line = ' '.join(words)
        rows.append(line)
    if replaced != set(expected):
        raise ValueError('Missing original bank driver')
    bank = '\n'.join(rows)+'\n'
    bank = bank.replace('.subckt '+BASE+' ', '.subckt '+name(profile)+' ', 1).replace('.ends '+BASE+'\n', '.ends '+name(profile)+'\n', 1)
    return cells, bank, dict(driver_models=expected, input_guard_um=[4, 4] if profile == 'fine3' else [3, 3],
                            fine_driver_guard_um=[3, 3], both_driver_rc_models_have_actual_physical_witnesses=True,
                            tg_widths_um=[1.68, 3.36], all_other_component_rc_preserved=True,
                            whole_bank_rc_retained=False, electrical_qualification_passed=False, qualified_phy=False)
