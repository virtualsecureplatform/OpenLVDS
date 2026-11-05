# SPDX-License-Identifier: GPL-3.0-only
"""Controlled native model/selector experiment, with borrowed component RC.

Regular-Vt PMOS changes invalidate the inverter's physical RC witness. Its
unchanged wiring RC is retained only to diagnose device versus selector delay.
All untouched buffers/fine units retain their exact extracted component RC.
"""
import re
import dcdl_tg_terminated_v6 as baseline
from build_compound_drivers_v3 import cell_definition
from spice_library import replace

VERSION = 'native-tg-selector-and-driver-pmos-flavor-isolation-v9.1'
PROFILES = {'hvt_quad': (False, 2), 'regular_double': (True, 1),
            'regular_quad': (True, 2)}
HVT = 'sky130_fd_pr__pfet_01v8_hvt'
REGULAR = 'sky130_fd_pr__pfet_01v8'


def name(profile):
    if profile not in PROFILES:
        raise ValueError('Unknown driver/selector diagnostic profile')
    return 'openlvds_dcdl_tg_c16_f32_'+profile+'_v9'


def transform(cells, bank, profile):
    name(profile)
    regular, multiplier = PROFILES[profile]
    model = baseline.previous.INVERTER
    inverter = cell_definition(cells, model)
    matches = re.findall(r'(?m)^X\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+'+HVT+r'\s', inverter)
    if len(matches) != 8 or inverter.count(HVT) != 8:
        raise ValueError('Require all eight unchanged HVT PMOS fingers in the guarded inverter')
    changed = inverter.replace(HVT, REGULAR) if regular else inverter
    cells = replace(cells, model, changed.rstrip())
    tg = baseline.previous.tg_source(baseline.PROFILE)
    if cell_definition(cells, baseline.previous.tg_name(baseline.PROFILE)).strip() != tg.strip():
        raise ValueError('Require the original double-TG source geometry')
    n, p = baseline.previous.PROFILES[baseline.PROFILE]
    def geometry(width):
        return f'w={width:g} l=0.15 ad={width*.29:.9g} as={width*.29:.9g} pd={2*(width+.29):.9g} ps={2*(width+.29):.9g}'
    # Parameter-string replacement must not accidentally resize the new N
    # device a second time when its width equals the original P width.
    rows = tg.splitlines()
    widened = '\n'.join(row[:row.index('w=')]+geometry((n if row.startswith('XN ') else p)*multiplier)
                        if row.startswith(('XN ', 'XP ')) else row for row in rows)+'\n'
    cells = replace(cells, baseline.previous.tg_name(baseline.PROFILE), widened.rstrip())
    old = baseline.name()
    if bank.count('.subckt '+old+' ') != 1 or bank.count('.ends '+old+'\n') != 1:
        raise ValueError('Require the original complete terminated bank')
    bank = bank.replace('.subckt '+old+' ', '.subckt '+name(profile)+' ', 1).replace('.ends '+old+'\n', '.ends '+name(profile)+'\n', 1)
    return cells, bank, dict(regular_pmos_in_input_and_fine_driver=regular,
                             changed_pmos_instances=16 if regular else 0,
                             tg_widths_um=[n*multiplier, p*multiplier],
                             tg_junctions='Nonzero prelayout estimates scaled with width',
                             inverter_rc='Borrowed original wiring RC; new device flavor has no physical proof' if regular else 'Original exact component RC',
                             untouched_component_rc_preserved=True,
                             whole_bank_rc_retained=False, electrical_qualification_passed=False, qualified_phy=False)
