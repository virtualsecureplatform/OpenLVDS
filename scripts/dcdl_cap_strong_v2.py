# SPDX-License-Identifier: GPL-3.0-only
"""Stronger return merge with digitally controlled MIM fine-bank inputs."""
import dcdl_cap_bank_v2 as bank
VERSION='dcdl-mim-strong-return-v2.1'


def circuit(coarse):
    text,devices=bank.circuit('mim2x2',coarse,0)
    header='.subckt dcdl_source IN OUT VDD VSS'
    controls=[pin for i in range(31) for pin in (f'E{i}',f'EB{i}')]
    text=text.replace(header,header+' '+' '.join(controls))
    before='Xm0 t0 p0 VSS VSS VDD VDD r0 sky130_fd_sc_hd__nand2_4'
    if text.count(before)!=1:raise ValueError('Original return merge changed')
    text=text.replace(before,before.replace('nand2_4','nand2_8'))
    for i in range(31):
        for offset,name,gate in [(0,f'XSWN{i}',f'E{i}'),(1,f'XSWP{i}',f'EB{i}'),(2,f'XCLR{i}',f'EB{i}')]:
            old=devices[3*i+offset];tokens=next(line.split() for line in text.splitlines() if line.startswith(name+' '))
            before=' '.join(tokens);tokens[2]=gate;text=text.replace(before,' '.join(tokens))
            devices[3*i+offset]=dict(old,terminals=[old['terminals'][0],gate,*old['terminals'][2:]])
    return text,devices
