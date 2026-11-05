# SPDX-License-Identifier: GPL-3.0-only
"""Replace one or both actual low-Vt driver components with real 2x2 guards."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import actual_nlvt_bank_v31 as baseline
import verify_nlvt_guard2_v35 as proof
from spice_library import checked_netlist, replace
from uniform_tree_parasitic_isolation_v4 import isolate

ROOT = baseline.ROOT
PROFILES = {'fine2': ('Xfine_driver',), 'both2': ('Xinput_inverse','Xfine_driver')}
OLD = proof.physical.OLD
MODEL = proof.NAME
NATIVE = baseline.NATIVE


def name(profile):
    if profile not in PROFILES: raise ValueError('Unknown 2x2 driver-guard profile')
    return 'openlvds_dcdl_c16_f32_'+profile+'_v36'


def witnesses(evidence):
    i = json.loads((evidence/'manifest.json').read_text())['identity']
    if (evidence.parent != ROOT/'build/diagnostics'/proof.CONTEXT or i['version'] != proof.VERSION
            or evidence.name != hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or proof.sha(Path(i['cad_python']['path'])) != i['cad_python']['sha256']):
        raise ValueError('Require independently verified native low-Vt 2x2 guard')
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join(dict.fromkeys(str(Path(t['path']).parent) for t in i['tools'].values()))+os.pathsep+env['PATH']
    code = ('import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); '
            'import verify_nlvt_guard2_v35 as p; p.bound(Path(sys.argv[2]))')
    subprocess.run([i['cad_python']['path'],'-c',code,str(ROOT),str(evidence)],env=env,check=True)
    r = json.loads((evidence/'summary.json').read_text()); parent = ROOT/i['parent']
    pi = json.loads((parent/'manifest.json').read_text())['identity']
    paths = [evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in i['inputs']]]
    paths += [ROOT/n for n in pi['inputs']]
    paths += [ROOT/r['extraction'][k] for k in ('raw_netlist','netlist')]
    return checked_netlist(r['extraction']),paths,pi,dict(cad_python=i['cad_python'],evidence=str(evidence.relative_to(ROOT)),actual_guard2_component_rc=True)


def transform(cells, bank, guard, profile):
    name(profile); definitions = NATIVE.definitions(cells); actual = NATIVE.definitions(guard)
    if set(actual) != {MODEL} or OLD not in definitions or definitions[OLD][0] != actual[MODEL][0]:
        raise ValueError('Actual smaller-guard component interface changed')
    # The complete source/RC geometry check is independent of installation.
    from build_compound_drivers_v3 import cell_definition
    old_native,_ = isolate(cell_definition(cells,OLD),OLD); new_native,_ = isolate(guard,MODEL)
    proof.physical.native_check(old_native,new_native)
    result = cells+'\n'+guard if profile == 'fine2' else replace(cells,OLD,guard.rstrip())
    after = NATIVE.definitions(result)
    expected = set(definitions)|{MODEL} if profile == 'fine2' else (set(definitions)-{OLD})|{MODEL}
    if set(after) != expected or any(after[k] != definitions[k] for k in definitions if k != OLD):
        raise ValueError('Smaller-guard installation changed unrelated components')
    if profile == 'fine2' and after[OLD] != definitions[OLD]: raise ValueError('Input driver 3x3 guard changed')
    rows = []; drivers = []; changed = []
    for line in bank.splitlines():
        w = line.split()
        if w and w[-1] == OLD:
            if w[0] not in ('Xinput_inverse','Xfine_driver'): raise ValueError('Unexpected original guard-driver instance')
            drivers.append(w[0])
            if w[0] in PROFILES[profile]:
                changed.append(w[0]);w[-1]=MODEL;line=' '.join(w)
        rows.append(line)
    if set(drivers) != {'Xinput_inverse','Xfine_driver'} or len(drivers) != 2 or set(changed) != set(PROFILES[profile]) or len(changed) != len(PROFILES[profile]):
        raise ValueError('Missing, duplicated or unexpected guard-driver replacement')
    bank='\n'.join(rows)+'\n';root=baseline.name('actual_nlvt')
    if bank.count('.subckt '+root+' ') != 1 or bank.count('.ends '+root+'\n') != 1:
        raise ValueError('Require complete actual-component-RC bank')
    bank=bank.replace('.subckt '+root+' ','.subckt '+name(profile)+' ',1).replace('.ends '+root+'\n','.ends '+name(profile)+'\n',1)
    return result,bank,dict(guard2_instances=changed,guard2_component_rc_retained=True,
                           actual_component_counts=dict(tg=20,inv3=2-len(changed),inv2=len(changed),bufpair=16),
                           component_rc_physically_equivalent=True,whole_bank_rc_retained=False,qualified_phy=False)
