#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install an optional Ubuntu ngspice runtime entirely under OpenLVDS/build.

Run on the Ubuntu host. The bundled loader/libraries let the binary run inside
the pinned Apptainer image without modifying that image or the host packages.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='42+ds-3build1'

def main():
    out=ROOT/'build/tools';download=out/'ngspice-download';download.mkdir(parents=True,exist_ok=True)
    deb=download/f'ngspice_{VERSION}_amd64.deb'
    if not deb.exists():subprocess.run(['apt-get','download','ngspice='+VERSION],cwd=download,check=True)
    package=out/'ngspice-root';binary=package/'usr/bin/ngspice'
    # Extract just the executable, avoiding hundreds of example files on NFS.
    payload=subprocess.run(['dpkg-deb','--fsys-tarfile',str(deb)],capture_output=True,check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        member=next(m for m in archive.getmembers() if m.name.lstrip('./')=='usr/bin/ngspice')
        binary.parent.mkdir(parents=True,exist_ok=True)
        binary.write_bytes(archive.extractfile(member).read());binary.chmod(0o755)
    result=subprocess.run(['ldd',str(binary)],capture_output=True,text=True,check=True)
    if 'not found' in result.stdout:raise RuntimeError(result.stdout)
    runtime=out/'ngspice-runtime';runtime.mkdir(parents=True,exist_ok=True)
    for line in result.stdout.splitlines():
        m=re.search(r'=> (/[^ ]+)|^\s*(/[^ ]+)',line)
        if m:
            path=Path(m[1] or m[2]);shutil.copyfile(path,runtime/path.name)
    for file in runtime.iterdir():file.chmod(0o755)
    manifest=dict(package_version=VERSION,package_sha256=hashlib.sha256(deb.read_bytes()).hexdigest(),
        files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in [binary,*sorted(runtime.iterdir())]})
    (out/'ngspice.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Installed optional ngspice runtime in',out)

if __name__=='__main__':main()
