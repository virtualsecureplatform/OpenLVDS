# SPDX-License-Identifier: GPL-3.0-only
"""Legal NMOS-low-Vt isolation using the complete failed component-RC network.

Retain W/L, junctions and every R/C. Changed implant geometry requires new
physical proof. Fine switches and all decoder/control cells remain unchanged.
"""
from build_compound_drivers_v3 import cell_definition
from spice_library import replace
import tg_component_bank_v23 as baseline

N = 'sky130_fd_pr__nfet_01v8'
NLVT = 'sky130_fd_pr__nfet_01v8_lvt'
PHVT = 'sky130_fd_pr__pfet_01v8_hvt'
P = 'sky130_fd_pr__pfet_01v8'
TG = baseline.MODEL
INV = baseline.previous.SMALL
BUF = baseline.controls.BUFFER
PROFILES = {'tg_nlvt': (TG,), 'data_nlvt': (TG, INV, BUF)}


def name(profile):
    if profile not in PROFILES:
        raise ValueError('Unknown NMOS-low-Vt isolation profile')
    return 'openlvds_dcdl_c16_f32_'+profile+'_v25'


def transform(cells, bank, profile):
    name(profile)
    definitions = baseline.previous.native.definitions(cells); renames = {}; changes = []
    result = cells
    for model in PROFILES[profile]:
        text = cell_definition(cells, model); ports, body = definitions[model]
        ncount = pcount = 0
        for w in body:
            if not w[0].startswith('X'):
                continue
            end = next((i for i, token in enumerate(w) if '=' in token), len(w)); child = w[end-1]
            if child == N:
                params = dict(token.split('=', 1) for token in w[end:])
                if float(params['l']) != .15 or float(params['w']) < .42:
                    raise ValueError('Changed NMOS geometry is outside the verified local LVT PCell limits')
                ncount += 1
            elif child == PHVT:
                if model != BUF:
                    raise ValueError('Unexpected HVT PMOS in the selected data component')
                pcount += 1
            elif child not in (P, 'sky130_fd_pr__cap_mim_m3_1'):
                raise ValueError('Unexpected active model in data-path flavor isolation')
        if not ncount:
            raise ValueError('Selected data component has no original regular NMOS')
        new_model = model+'_nlvt_diagnostic_v25'; renames[model] = new_model
        changed = text.replace(N, NLVT).replace(PHVT, P)
        changed = changed.replace('.subckt '+model+' ', '.subckt '+new_model+' ', 1).replace('.ends '+model, '.ends '+new_model)
        result = replace(result, model, changed.rstrip())
        changes.append(dict(original_model=model, diagnostic_model=new_model,
                            nmos_flavor_changes_per_instance=ncount, hvt_to_regular_pmos_per_instance=pcount))
    root = baseline.name('both3')
    if bank.count('.subckt '+root+' ') != 1 or bank.count('.ends '+root+'\n') != 1:
        raise ValueError('Require the complete actual-TG-RC both3 bank')
    rows = []; counts = {m: 0 for m in renames}
    for line in bank.splitlines():
        w = line.split()
        if w and w[-1] in renames:
            counts[w[-1]] += 1; w[-1] = renames[w[-1]]; line = ' '.join(w)
        rows.append(line)
    expected = {TG: 20} if profile == 'tg_nlvt' else {TG: 20, INV: 2, BUF: 16}
    if counts != expected:
        raise ValueError('Original data-component instance counts changed')
    bank = '\n'.join(rows)+'\n'
    bank = bank.replace('.subckt '+root+' ', '.subckt '+name(profile)+' ', 1).replace('.ends '+root+'\n', '.ends '+name(profile)+'\n', 1)
    return result, bank, dict(changed_components=changes, changed_instance_counts=counts,
                              native_nmos_model_changes=sum(c['nmos_flavor_changes_per_instance']*counts[c['original_model']] for c in changes),
                              native_pmos_model_changes=sum(c['hvt_to_regular_pmos_per_instance']*counts[c['original_model']] for c in changes),
                              geometry_and_rc_tokens_retained=True, new_implant_physical_proof=False,
                              component_rc_physically_equivalent=False, whole_bank_rc_retained=False, qualified_phy=False)
