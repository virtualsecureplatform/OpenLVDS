# SPDX-License-Identifier: GPL-3.0-only
"""Assemble checked, explicitly ordered schematic / extracted PHY libraries."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def replace(text,name,body):
    pattern=r'(?ims)^\.subckt[ \t]+'+re.escape(name)+r'[ \t]+.*?^\.ends(?:[ \t]+[^\n]*)?$'
    text,count=re.subn(pattern,lambda _:body,text)
    if count!=1:raise ValueError(f'Expected one definition of {name}, found {count}')
    return text

def checked_netlist(info):
    path=ROOT/info['netlist'];data=path.read_bytes()
    if not info['passed'] or not info.get('ports_verified'):
        raise ValueError(f'Unqualified extraction {path}')
    if hashlib.sha256(data).hexdigest()!=info['netlist_sha256']:
        raise ValueError(f'Changed extracted network {path}')
    header=re.search(r'(?im)^\.subckt[^\n]*(?:\n\+[^\n]*)*',data.decode())
    if not header or header[0].replace('\n+',' ').split()[2:]!=info['ports']:
        raise ValueError(f'Changed extracted terminal order {path}')
    return data.decode()

def digital_current(name,info):
    which={'lvds_pfd':'pfd','openlvds_tx_core':'tx','openlvds_ddr_rx':'rx'}[name]
    physical=json.loads((ROOT/f'build/physical/{which}/summary.json').read_text())
    sources=[ROOT/'rtl/openlvds_reset.v',ROOT/f'rtl/{name}.v']
    if which=='tx':sources.extend([ROOT/'rtl/openlvds_ddr_tx.v',ROOT/'sky130/tx_blackboxes.v'])
    if which=='pfd':sources=[ROOT/'sky130/lvds_pfd.v',ROOT/'sky130/pfd_blackboxes.v']
    sources.extend([ROOT/f'constraints/{which}.sdc',ROOT/f'build/physical/{which}/config.json'])
    current=hashlib.sha256(b''.join(p.read_bytes() for p in sources)).hexdigest()
    path=ROOT/physical['run']/'final/gds'/f'{name}.gds'
    if not physical['passed'] or physical['source_sha256']!=current or current!=info['source_sha256'] or hashlib.sha256(path.read_bytes()).hexdigest()!=info['gds_sha256']:
        raise ValueError(name+': digital RC extraction is stale')
    return info

def library(extracted=False,digital=False,fast=False,designs=None):
    source=(ROOT/'analog/openlvds.spice').read_bytes();text=source.decode();inputs={};models={}
    source_hash=hashlib.sha256(source).hexdigest()
    fast_models=json.loads((ROOT/'build/extracted/fast.json').read_text())['designs'] if fast else {}
    def selected(name,info):
        if not fast:return info
        replacement=fast_models[name]
        if replacement['exact_sha256']!=info['netlist_sha256']:
            raise ValueError(f'{name}: fast model is stale')
        return replacement
    if extracted:
        manifest=json.loads((ROOT/'build/extracted/current.json').read_text())
        requested=set(designs) if designs is not None else {'openlvds_driver_core','openlvds_receiver_core','openlvds_delay_line','openlvds_dll_analog','lvds_bias'}
        if requested-set(manifest['designs']):raise ValueError('Required analog extraction is missing')
        physical=json.loads((ROOT/'build/layout/current.json').read_text())
        from layout import circuits,flatten,schematic_text
        definitions=circuits(source.decode())
        for name,info in manifest['designs'].items():
            if designs is not None and name not in designs:continue
            expected=physical['designs'][name]
            pins,devices=flatten(definitions,name)
            if info['ports']!=pins:raise ValueError(name+': extracted terminal order differs from the schematic')
            current_scope=hashlib.sha256(schematic_text(name,pins,devices).encode()).hexdigest()
            if not expected['passed'] or expected['lvs_source_sha256']!=current_scope:
                raise ValueError(name+': physical schematic scope is stale')
            if hashlib.sha256((ROOT/expected['gds']).read_bytes()).hexdigest()!=info['gds_sha256']:
                raise ValueError(name+': extracted GDS is stale')
            if info['source_sha256']!=source_hash and info.get('source_scope_sha256')!=expected['lvs_source_sha256']:
                raise ValueError(f'{name}: extracted GDS belongs to another schematic')
            info=selected(name,info)
            text=replace(text,name,checked_netlist(info));inputs[name]=info['netlist_sha256']
        # PFD layout pins use VPWR/VGND; the analog schematic interface uses
        # VDDD/VSS. Bind by NAME, never assume extracted positional order.
        if designs is None or 'openlvds_dll_analog' in designs:
            manifest=json.loads((ROOT/'build/extracted/digital.json').read_text())
            info=selected('lvds_pfd',digital_current('lvds_pfd',manifest['designs']['lvds_pfd']));body=checked_netlist(info)
            body=re.sub(r'(?im)^(\.subckt[ \t]+)lvds_pfd\b',r'\1lvds_pfd_physical',body)
            expected=['REF','FB','RESET_N','PD_ENABLE','UP','DN','ERR','VDDD','VSS']
            mapping={x:x for x in expected};mapping.update(VPWR='VDDD',VGND='VSS')
            pins=[mapping[x] for x in info['ports']]
            adapter='.subckt lvds_pfd '+' '.join(expected)+'\nXPHYS '+' '.join(pins)+' lvds_pfd_physical\n.ends lvds_pfd'
            text=replace(text,'lvds_pfd',body+'\n'+adapter)
            inputs['lvds_pfd']=info['netlist_sha256']
    if digital:
        manifest=json.loads((ROOT/'build/extracted/digital.json').read_text())
        for name in ['openlvds_tx_core','openlvds_ddr_rx']:
            info=selected(name,digital_current(name,manifest['designs'][name]));text+='\n'+checked_netlist(info)
            inputs[name]=info['netlist_sha256'];models[name]=info
    return text.encode(),inputs,models
