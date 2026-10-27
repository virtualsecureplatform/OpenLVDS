#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect pinned Magic PCell terminals before generating interconnect."""
import os
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
out=root/'build/pcell_probe';out.mkdir(parents=True,exist_ok=True)
tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/magic'
script=out/'probe.tcl'
script.write_text('''drc off
crashbackups disable
locking disable
load probe -silent
set p [sky130::sky130_fd_pr__nfet_g5v0d10v5_defaults]
dict set p w 2
dict set p l 0.5
sky130::sky130_fd_pr__nfet_g5v0d10v5_draw $p
puts "SCALE [cif scale out]"
save probe
puts "PORT_FIRST [port first]"
foreach {cell model params} {
    res sky130_fd_pr__res_high_po_0p35 {l 8.5}
    cap sky130_fd_pr__cap_mim_m3_1 {w 4 l 4.5}
    fingers sky130_fd_pr__nfet_g5v0d10v5 {w 5 l 0.5 nf 4 conn_gates 1}
} {
    load $cell -silent
    set p [sky130::${model}_defaults]
    set p [dict merge $p $params]
    sky130::${model}_draw $p
    save $cell
}
quit -noprompt
''')
result=subprocess.run(['magic','-dnull','-noconsole','-rcfile',str(tech/'sky130A.magicrc'),str(script)],
                      cwd=out,text=True,capture_output=True)
(out/'magic.log').write_text(result.stdout+result.stderr)
print(result.stdout[-3500:]);print(result.stderr[-1000:])
for name in ['probe','res','cap','fingers']:
    p=out/(name+'.mag')
    if p.exists(): print(name, p.read_text().split('<< labels >>')[-1])
