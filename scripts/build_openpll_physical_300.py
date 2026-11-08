#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rebuild pinned OpenPLL DCO geometry in a private, provenance-bound source copy."""
from datetime import datetime,timezone
import hashlib,io,json,os,subprocess,tarfile
from pathlib import Path
from clocking_profile_300 import load,ROOT

def run():
    profile=load();pin=profile['requirements']['openpll_commit']
    repo=ROOT/'thirdparties/OpenPLL'
    if subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()!=pin:
        raise ValueError('OpenPLL pin mismatch')
    archive=subprocess.check_output(['git','-C',str(repo),'archive',pin])
    out=ROOT/'build/diagnostics/openpll_physical_300'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source=out/'source';source.mkdir(parents=True,exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(source,filter='data')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    identity=dict(openpll_commit=pin,archive_sha256=hashlib.sha256(archive).hexdigest(),
        profile_sha256=sha(ROOT/'clocking_300mhz.json'),producer_sha256=sha(Path(__file__)),
        pdk_version=profile['requirements']['pdk_version'],coarse_code=2,fine_code=12,qualified_phy=False)
    (out/'manifest.json').write_text(json.dumps(identity,indent=2)+'\n');print(out,flush=True)
    commands=[(['librelane','--manual-pdk','--pdk-root',os.environ['PDK_ROOT'],'-p','sky130A','-s','sky130_fd_sc_hd','--condensed','--hide-progress-bar','--run-tag','openlvds_300','openlane/IntegerPLL_DCO_EINVP_COARSE/config_modern.json'],'physical.log'),
              (['bash','scripts/dco_magic_rcx.sh'],'extraction.log')]
    env=dict(os.environ,DESIGN_DIR='openlane/IntegerPLL_DCO_EINVP_COARSE',RUN_TAG='openlvds_300',LIBRELANE_ROOT='/opt/librelane')
    for command,name in commands:
        with (out/name).open('w') as log:
            result=subprocess.run(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            (out/'state.json').write_text(json.dumps(dict(status='failed',stage=name,returncode=result.returncode,qualified_phy=False))+'\n')
            result.check_returncode()
    rc=source/'openlane/IntegerPLL_DCO_EINVP_COARSE/runs/openlvds_300/rcx-magic/IntegerPLL_DCO_EINVP_COARSE.rcx.spice'
    if not rc.is_file():raise ValueError('Expected extracted DCO missing')
    (out/'summary.json').write_text(json.dumps(dict(identity=identity,netlist=str(rc.relative_to(ROOT)),netlist_sha256=sha(rc),
        scope='Pinned DCO physical rebuild and extraction only; transient clock/stress qualification remains required',qualified_phy=False),indent=2)+'\n')
    (out/'state.json').write_text(json.dumps(dict(status='complete',qualified_phy=False))+'\n')
    return out
if __name__=='__main__':run()
