#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Publish the asynchronous I/O macro views and fail-closed gate receipts.

`publish` freezes a candidate: every release view of both macros plus the
hashes of the sources and tools that produced it. `receipts` then judges each
release gate of qualification_io_300.json from recorded evidence only; it
never simulates. A gate without complete, current evidence is written as
`fail` with the reason, never omitted and never assumed.
"""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
POLICY='qualification_io_300.json'
RELEASE=ROOT/'build/release_io_300'
BENCH=ROOT/'build/io_300'
MACROS=dict(openlvds_io_tx='driver',openlvds_io_rx='receiver')
SOURCES=['analog/openlvds.spice','io_300.json','scripts/layout.py','scripts/lvs_utils.py','scripts/extract.py','scripts/reduce_rc.py',
    'scripts/spice_library.py','scripts/verify_analog.py','scripts/evidence_scope.py','scripts/xyce_profile_300.py',
    'sky130/openlvds_io.v','models/openlvds_io_functional.v','constraints/io_300/openlvds_io_tx.sdc',
    'constraints/io_300/openlvds_io_rx.sdc','docs/io-300-integration.md','docs/io-300-test.md']
TOOLS=['build/apptainer/openlvds.sif.sha256','build/tools/ngspice.json']
# Agreement required between two simulations of the same nominal bench.
TOLERANCE=dict(model_compatibility=dict(v=.010,ps=25.),numerical_refinement=dict(v=.005,ps=10.),exact_rc_equivalence=dict(v=.002,ps=5.))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()

def rel(path):return str(Path(path).resolve().relative_to(ROOT))

def load(path):return json.loads(Path(path).read_text())

def contract():
    terms=load(ROOT/'io_300.json')
    if terms.get('schema')!='openlvds-io-300-v1':raise ValueError('Unsupported contract')
    return terms,sha(ROOT/'io_300.json')

def points(req):return list(itertools.product(req['process_corners'],req['temperatures_c']))


class Evidence:
    """Collects named checks and the exact files they were read from."""
    def __init__(self):self.checks={};self.files={};self.notes={}
    def read(self,path):
        path=Path(path)
        if not path.is_file():raise FileNotFoundError('Missing evidence: '+rel(path) if path.is_absolute() else str(path))
        self.files[rel(path)]=sha(path);return load(path)
    def check(self,name,value):self.checks[name]=bool(value)
    def attempt(self,name,function):
        try:function()
        except (OSError,ValueError,KeyError,TypeError,IndexError,json.JSONDecodeError) as error:
            self.checks[name]=False;self.notes[name]=str(error)


def netlist_elements(path):
    """Devices, resistors and capacitors of an extracted RC netlist, keyed by net.

    Magic numbers the resistive sub-nodes of a net (`NET.t7`, `NET.n12`) and
    orders elements differently on every run, so two extractions of the same
    layout are never byte-identical; summed capacitances can also differ in
    the last printed digit.
    """
    from reduce_rc import number
    net=lambda node:re.sub(r'\.[tn]\d+$','',node)
    text=re.sub(r'\n\+',' ',Path(path).read_text());devices=[];passive=dict(R={},C={});ports=None
    for line in text.splitlines():
        words=line.split()
        if not words or words[0][0]=='*':continue
        kind=words[0][0].upper()
        if words[0].lower()=='.subckt':ports=words[1:]
        elif kind=='X':
            first=next((i for i,w in enumerate(words) if '=' in w),len(words))
            devices.append(' '.join([words[first-1],*map(net,words[1:first-1]),*sorted(words[first:])]))
        elif kind in passive:passive[kind].setdefault(tuple(sorted(map(net,words[1:3]))),[]).append(number(words[3]))
    if ports is None or not devices or not passive['R'] or not passive['C']:raise ValueError('Not an extracted RC netlist: '+str(path))
    return ports,sorted(devices),passive


def netlists_equivalent(first,second,rtol=1e-4):
    """Same devices on the same nets and the same R/C values between the same nets."""
    a,b=netlist_elements(first),netlist_elements(second);worst=0.
    same=a[0]==b[0] and a[1]==b[1]
    for kind in 'RC':
        same=same and a[2][kind].keys()==b[2][kind].keys()
        if not same:break
        for key,values in a[2][kind].items():
            other=sorted(b[2][kind][key]);values=sorted(values)
            if len(values)!=len(other):same=False;break
            for x,y in zip(values,other):worst=max(worst,abs(x-y)/max(abs(x),abs(y),1e-30))
    return dict(equivalent=bool(same and worst<=rtol),max_relative_difference=worst,relative_tolerance=rtol,devices=len(a[1]),
        resistors=sum(map(len,a[2]['R'].values())),capacitors=sum(map(len,a[2]['C'].values())))


def physical():
    """Current layout, signoff and extraction records for both macros, cross-checked."""
    source=sha(ROOT/'analog/openlvds.spice')
    layout=load(ROOT/'build/layout/current.json');signoff=load(BENCH/'signoff/current.json');extracted=load(ROOT/'build/extracted/current.json')
    if layout['source_sha256']!=source or signoff['source_sha256']!=source:raise ValueError('Layout or signoff belongs to another schematic')
    result={}
    for macro in MACROS:
        info=layout['designs'][macro];rc=extracted['designs'][macro];sign=signoff['designs'][macro]
        gds=ROOT/info['gds'];digest=sha(gds)
        if not (info['passed'] and rc['passed'] and sign['passed']):raise ValueError(macro+': layout, extraction or signoff failed')
        if rc['gds_sha256']!=digest or sign['gds_sha256']!=digest:raise ValueError(macro+': extraction or signoff used another GDS')
        if rc.get('source_scope_sha256')!=info['lvs_source_sha256']:raise ValueError(macro+': extraction belongs to another netlist')
        if sha(ROOT/rc['netlist'])!=rc['netlist_sha256']:raise ValueError(macro+': extracted netlist changed')
        result[macro]=dict(layout=info,extraction=rc,signoff=sign,gds=gds,gds_sha256=digest)
    return result


def expected_scopes(extracted=True,raw=False):
    """Scope hash each bench must carry for the current schematic or extracted macros."""
    from spice_library import library
    from evidence_scope import scope_hash
    data=library(extracted=True,designs=set(MACROS),raw=raw)[0] if extracted else (ROOT/'analog/openlvds.spice').read_bytes()
    return {test:scope_hash(data,test,True) for test in ['driver','receiver','link']}


def case(evidence,folder,name,binding,scopes,simulator='xyce'):
    """One bench summary, accepted only if it is passing, complete and current."""
    row=evidence.read(folder/name/'summary.json');test=name.split('_')[0]
    if row.get('passed') is not True:raise ValueError(name+': '+str(row.get('error','failed')))
    if row.get('requirements_sha256')!=binding or row.get('contract')!='io_300.json':raise ValueError(name+': other contract')
    if row.get('simulation_scope_sha256')!=scopes[test]:raise ValueError(name+': stale circuit')
    if row.get('simulator')!=simulator:raise ValueError(name+': unexpected simulator')
    wave=folder/name/'bench.cir.prn'
    if row.get('waveform_sha256')!=sha(wave):raise ValueError(name+': waveform changed')
    return row


# ---------------------------------------------------------------- views

def schematic_closure(top):
    text=(ROOT/'analog/openlvds.spice').read_text()
    blocks={m[1]:m[0] for m in re.finditer(r'(?ims)^\.subckt[ \t]+(\S+)[ \t]+.*?^\.ends[^\n]*',text)}
    order=[]
    def visit(name):
        for line in blocks[name].splitlines():
            words=line.split()
            if words and words[0][0].upper()=='X':
                end=next((i for i,w in enumerate(words) if '=' in w),len(words))
                if words[end-1] in blocks and words[end-1] not in order:visit(words[end-1])
        if name not in order:order.append(name)
    visit(top)
    return '* SPDX-License-Identifier: GPL-3.0-only\n* Hierarchical schematic of '+top+' from analog/openlvds.spice\n\n'+'\n\n'.join(blocks[n] for n in order)+'\n'


def table(rows):return ', \\\n          '.join('"'+', '.join(f'{v:.5f}' for v in row)+'"' for row in rows)

def liberty(macro,process,temp,req,info,timing):
    """Timing view from extracted transistor-level measurements at one PVT point."""
    name=f'{macro}_{process}_{temp:03d}C';area=info['width_um']*info['height_um']
    head=f'''/* SPDX-License-Identifier: GPL-3.0-only
   {macro}: {process} process, {temp} C, VDDIO {req["analog_supply_v"]} V, VDDD {req["digital_supply_v"]} V.
   Measured on the layout-extracted macro by scripts/verify_analog.py --test timing.
   Analog pins carry no timing arcs; see the integration guide. */
library ({name}) {{
  technology (cmos);
  delay_model : table_lookup;
  time_unit : "1ns";
  voltage_unit : "1V";
  current_unit : "1mA";
  pulling_resistance_unit : "1kohm";
  leakage_power_unit : "1nW";
  capacitive_load_unit (1, pf);
  input_threshold_pct_rise : 50;
  input_threshold_pct_fall : 50;
  output_threshold_pct_rise : 50;
  output_threshold_pct_fall : 50;
  slew_lower_threshold_pct_rise : 20;
  slew_upper_threshold_pct_rise : 80;
  slew_lower_threshold_pct_fall : 20;
  slew_upper_threshold_pct_fall : 80;
  slew_derate_from_library : 1.0;
  nom_process : 1.0;
  nom_temperature : {temp};
  nom_voltage : {req["digital_supply_v"]};
  voltage_map (VDDIO, {req["analog_supply_v"]});
  voltage_map (VDDD, {req["digital_supply_v"]});
  voltage_map (VSS, 0.0);
  operating_conditions ({process}_{temp:03d}C) {{
    process : 1.0;
    temperature : {temp};
    voltage : {req["digital_supply_v"]};
  }}
  default_operating_conditions : {process}_{temp:03d}C;
'''
    supplies='''    pg_pin (VDDIO) { voltage_name : VDDIO; pg_type : primary_power; }
    pg_pin (VDDD) { voltage_name : VDDD; pg_type : primary_power; }
    pg_pin (VSS) { voltage_name : VSS; pg_type : primary_ground; }
'''
    def analog(pin,capacitance=None):
        extra=f' capacitance : {capacitance:.5f};' if capacitance is not None else ''
        return f'    pin ({pin}) {{ direction : inout;{extra} related_power_pin : VDDIO; related_ground_pin : VSS; }}\n'
    cell=f'  cell ({macro}) {{\n    area : {area:.3f};\n    is_macro_cell : true;\n    dont_touch : true;\n    dont_use : true;\n'+supplies
    if macro=='openlvds_io_tx':
        cell+=(f'    pin (D) {{ direction : input; capacitance : {timing["input_capacitance_pf"]:.5f}; max_transition : 0.5;'
               ' related_power_pin : VDDD; related_ground_pin : VSS; }\n')
        cell+=''.join(analog(p) for p in ['OUTP','OUTN','VREF','IREF'])
        return head+cell+'  }\n}\n'
    slews=[x/1000 for x in timing['input_transition_20_80_ps']];loads=[x/1000 for x in timing['output_load_ff']]
    head+=f'''  lu_table_template (rx_delay) {{
    variable_1 : input_net_transition;
    variable_2 : total_output_net_capacitance;
    index_1 ("{', '.join(f'{v:.5f}' for v in slews)}");
    index_2 ("{', '.join(f'{v:.5f}' for v in loads)}");
  }}
'''
    cell+=analog('INP',timing['input_pin_capacitance_pf'])+analog('INN',timing['input_pin_capacitance_pf'])+analog('VREF')+analog('IREF')
    arcs=''.join(f'        {key} (rx_delay) {{\n          values ({table(timing[key])});\n        }}\n'
                 for key in ['cell_rise','rise_transition','cell_fall','fall_transition'])
    cell+=(f'    pin (Q) {{\n      direction : output;\n      function : "INP";\n      max_capacitance : {max(loads):.5f};\n'
           '      related_power_pin : VDDD;\n      related_ground_pin : VSS;\n'
           '      timing () {\n        related_pin : "INP";\n        timing_sense : positive_unate;\n'+arcs+'      }\n    }\n')
    return head+cell+'  }\n}\n'


def electrical_rows(macro,req,folder,binding,scopes):
    """Per-PVT measured table. Failed or missing points stay in the table as such."""
    rows=[]
    for process,temp in points(req):
        row=dict(macro=macro,process=process,temperature_c=temp)
        def take(name,keys,prefix=''):
            try:
                data=case(Evidence(),folder,name,binding,scopes)
                for key,source in keys.items():
                    value=data
                    for part in source.split('.'):value=value[part]
                    row[prefix+key]=value
            except (OSError,ValueError,KeyError,TypeError) as error:row[prefix+'error']=str(error)
        if macro=='openlvds_io_tx':
            take(f'driver_{process}_{temp}',dict(vod_min_v='differential_min_v',vod_max_v='differential_max_v',
                vcm_min_v='common_mode_min_v',vcm_max_v='common_mode_max_v',transition_min_ps='waveform.transition_min_ps',
                transition_max_ps='waveform.transition_max_ps',common_mode_pp_v='waveform.common_mode_pp_v',
                vod_imbalance_v='imbalance.differential_imbalance_v',vos_imbalance_v='imbalance.common_mode_imbalance_v',
                propagation_min_ps='propagation_min_ps',propagation_max_ps='propagation_max_ps',
                thin_oxide_span_v='stress.thin_oxide_terminal_span_v'))
            take(f'driver_timing_{process}_{temp}',dict(d_capacitance_pf='input_capacitance_pf'))
            take(f'driver_power_{process}_{temp}',dict(vddio_static_ma='quiet.vddio_ma',vddio_toggling_ma='active.vddio_ma',
                vddd_toggling_ma='active.vddd_ma',power_static_mw='quiet.power_mw',power_toggling_mw='active.power_mw',vref_ua='active.vref_ua'))
        else:
            take(f'receiver_{process}_{temp}',dict(thin_oxide_span_v='stress.thin_oxide_terminal_span_v'),'static_')
            for mhz in req['clock_test_mhz']:
                take(f'receiver_rate_{process}_{temp}_{mhz}m',dict(high_valid_min_ps='high_valid_min_ps',low_valid_min_ps='low_valid_min_ps'),f'rate_{mhz}m_')
            take(f'receiver_timing_{process}_{temp}',dict(input_capacitance_pf='input_pin_capacitance_pf'))
            take(f'receiver_power_{process}_{temp}',dict(vddio_static_ma='quiet.vddio_ma',vddio_toggling_ma='active.vddio_ma',
                vddd_toggling_ma='active.vddd_ma',power_static_mw='quiet.power_mw',power_toggling_mw='active.power_mw',vref_ua='active.vref_ua'))
        row['complete']=not any(k.endswith('error') for k in row)
        rows.append(row)
    return rows


def publish():
    terms,binding=contract();req=terms['requirements'];phys=physical();scopes=expected_scopes()
    extracted=BENCH/'analog_extracted';views={};out=RELEASE/'views'
    if out.exists():shutil.rmtree(out)
    def put(macro,view,name,data=None,source=None,**extra):
        target=out/macro/name;target.parent.mkdir(parents=True,exist_ok=True)
        if source is not None:shutil.copyfile(source,target)
        else:target.write_text(data)
        entry=dict(path=rel(target),sha256=sha(target),**extra)
        if view=='liberty':views[macro].setdefault(view,[]).append(entry)
        else:views[macro][view]=entry
    for macro,test in MACROS.items():
        views[macro]={};info=phys[macro]['layout'];gds=phys[macro]['gds'];short=macro.rsplit('_',1)[1]
        put(macro,'gds',macro+'.gds',source=gds)
        put(macro,'lef',macro+'.lef',source=gds.with_suffix('.lef'))
        put(macro,'cdl',macro+'.cdl',source=gds.with_suffix('.sch.spice'))
        put(macro,'schematic_spice',macro+'.spice',data=schematic_closure(macro))
        put(macro,'extracted_spice',macro+'.rcx.spice',source=ROOT/phys[macro]['extraction']['netlist'])
        put(macro,'verilog_blackbox','openlvds_io.v',source=ROOT/'sky130/openlvds_io.v')
        put(macro,'verilog_functional','openlvds_io_functional.v',source=ROOT/'models/openlvds_io_functional.v')
        put(macro,'sdc',macro+'.sdc',source=ROOT/f'constraints/io_300/{macro}.sdc')
        put(macro,'integration_guide','io-300-integration.md',source=ROOT/'docs/io-300-integration.md')
        put(macro,'test_guide','io-300-test.md',source=ROOT/'docs/io-300-test.md')
        for process,temp in points(req):
            timing=case(Evidence(),extracted,f'{test}_timing_{process}_{temp}',binding,scopes)
            put(macro,'liberty',f'lib/{macro}_{process}_{temp:03d}C.lib',data=liberty(macro,process,temp,req,info,timing),
                process=process,temperature_c=temp)
        rows=electrical_rows(macro,req,extracted,binding,scopes)
        columns=list(dict.fromkeys(k for row in rows for k in row))
        target=out/macro/f'{macro}_electrical.csv';target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('w',newline='') as file:
            writer=csv.DictWriter(file,columns);writer.writeheader();writer.writerows(rows)
        views[macro]['electrical_tables']=dict(path=rel(target),sha256=sha(target),complete=all(r['complete'] for r in rows))
    RELEASE.mkdir(parents=True,exist_ok=True)
    (RELEASE/'views.json').write_text(json.dumps(views,indent=2)+'\n')
    candidate=dict(schema='openlvds-io-300-candidate-v1',contract_sha256=binding,pdk=req['pdk'],pdk_version=req['pdk_version'],
        views_sha256=sha(RELEASE/'views.json'),macros={m:dict(gds_sha256=phys[m]['gds_sha256'],
            width_um=phys[m]['signoff']['density']['width_um'],height_um=phys[m]['signoff']['density']['height_um']) for m in MACROS},
        source_files={name:sha(ROOT/name) for name in SOURCES},tool_receipts={name:sha(ROOT/name) for name in TOOLS})
    (RELEASE/'candidate.json').write_text(json.dumps(candidate,indent=2)+'\n')
    print(json.dumps(dict(candidate_sha256=sha(RELEASE/'candidate.json'),views=sum(len(v) for v in views.values())),indent=2))
    return 0


# ---------------------------------------------------------------- gates

def compare(e,gate,reference,other,simulator_other='xyce',extracted=False,raw_other=False):
    """Same nominal benches from two runs must both pass and agree within tolerance."""
    terms,binding=contract();req=terms['requirements'];scopes=expected_scopes(extracted);other_scopes=expected_scopes(extracted,raw_other);limit=TOLERANCE[gate];worst=dict(v=0.,ps=0.)
    def close(kind,a,b):
        worst[kind]=max(worst[kind],abs(a-b));return abs(a-b)<=limit[kind]
    def driver():
        a=case(e,reference,'driver_tt_25',binding,scopes);b=case(e,other,'driver_tt_25',binding,other_scopes,simulator_other)
        e.check('driver_levels_agree',all(close('v',a[k],b[k]) for k in ['differential_min_v','differential_max_v','common_mode_min_v','common_mode_max_v']))
        e.check('driver_timing_agrees',all(close('ps',a[k],b[k]) for k in ['propagation_min_ps','propagation_max_ps']) and
            all(close('ps',a['waveform'][k],b['waveform'][k]) for k in ['transition_min_ps','transition_max_ps']))
        e.check('driver_common_mode_ripple_agrees',close('v',a['waveform']['common_mode_pp_v'],b['waveform']['common_mode_pp_v']))
    def receiver():
        a=case(e,reference,'receiver_tt_25',binding,scopes);b=case(e,other,'receiver_tt_25',binding,other_scopes,simulator_other)
        e.check('receiver_decisions_agree',[p['passed'] for p in a['points']]==[p['passed'] for p in b['points']])
        for mhz in req['clock_test_mhz']:
            name=f'receiver_rate_tt_25_{mhz}m';a=case(e,reference,name,binding,scopes);b=case(e,other,name,binding,other_scopes,simulator_other)
            e.check(f'receiver_rate_{mhz}m_agrees',all(close('ps',a[k],b[k]) for k in ['high_valid_min_ps','low_valid_min_ps']))
    e.attempt('driver_compared',driver);e.attempt('receiver_compared',receiver)
    e.notes['tolerance']=limit;e.notes['worst_difference']=worst

def gate_model_compatibility(e):
    compare(e,'model_compatibility',BENCH/'analog',BENCH/'analog_ngspice','ngspice')
    def warnings():
        import xyce_profile_300
        log=BENCH/'analog/driver_tt_25/xyce.log';e.files[rel(log)]=sha(log)
        found=xyce_profile_300.warnings(log.read_text())
        e.notes['xyce_model_version_substitutions']=sorted(set(map(tuple,found['version_substitutions'])))
        e.check('xyce_warnings_recorded',True)
    e.attempt('xyce_warnings_recorded',warnings)

def gate_numerical_refinement(e):compare(e,'numerical_refinement',BENCH/'analog',BENCH/'analog_refined')

def gate_exact_rc_equivalence(e):compare(e,'exact_rc_equivalence',BENCH/'analog_extracted',BENCH/'analog_extracted_raw',extracted=True,raw_other=True)

def gate_native_drc_lvs_rc(e):
    def run():
        for macro,info in physical().items():
            e.files[rel(info['gds'])]=info['gds_sha256']
            e.check(macro+'_magic_full_drc_clean',info['layout']['drc_count']=='0')
            e.check(macro+'_lvs_unique_match',info['layout']['lvs_passed'])
            e.check(macro+'_rc_extracted',info['extraction']['resistors']>0 and info['extraction']['capacitors']>0 and info['extraction']['ports_verified'])
        for name in ['build/layout/current.json','build/extracted/current.json']:e.files[name]=sha(ROOT/name)
    e.attempt('physical_records_current',run)

def gate_antenna_density_erc(e):
    def run():
        e.files['build/io_300/signoff/current.json']=sha(BENCH/'signoff/current.json')
        for macro,info in physical().items():
            for key,value in info['signoff']['checks'].items():e.check(f'{macro}_{key}',value)
    e.attempt('signoff_record_current',run)

def all_points(e,tests,folder=None,extra=lambda row:True):
    terms,binding=contract();req=terms['requirements'];scopes=expected_scopes();folder=folder or BENCH/'analog_extracted';rows=[]
    for process,temp in points(req):
        for name in tests(req,process,temp):
            def one(name=name):
                row=case(e,folder,name,binding,scopes);rows.append(row);e.check(name,extra(row))
            e.attempt(name,one)
    return rows

def gate_analog_tx_rx_15pvt(e):
    all_points(e,lambda req,p,t:[f'driver_{p}_{t}',f'receiver_{p}_{t}']+[f'receiver_rate_{p}_{t}_{m}m' for m in req['clock_test_mhz']])

def link_names(req,p,t):return [f'link_{p}_{t}_{m}m_{d:g}ns' for m in req['link_clock_mhz'] for d in req['channel']['delay_ns']]

def gate_async_link_eye(e):
    req=contract()[0]['requirements']
    enough=lambda row:row['bit_errors']==0 and row['bits']>=req['minimum_extracted_corner_bits']
    all_points(e,link_names,extra=enough)
    def nominal():
        binding=contract()[1];scopes=expected_scopes()
        e.check('nominal_bit_count',all(case(e,BENCH/'analog_extracted',n,binding,scopes)['bits']>=req['minimum_extracted_nominal_bits'] for n in link_names(req,'tt',25)))
    e.attempt('nominal_bit_count',nominal)

def gate_device_stress(e):
    stressed=lambda row:row['stress']['passed'] is True
    all_points(e,lambda req,p,t:[f'driver_{p}_{t}',f'receiver_{p}_{t}']+[f'receiver_rate_{p}_{t}_{m}m' for m in req['clock_test_mhz']]+link_names(req,p,t),extra=stressed)

def gate_offset_and_mismatch(e):
    binding=contract()[1]
    for test in ['receiver-mc','driver-mc']:
        def run(test=test):
            data=e.read(BENCH/f'analog_ngspice/summary_{test}_corners.json')
            e.check(test+'_contract',data.get('contract_sha256')==binding)
            e.check(test+'_sample_plan_complete',data.get('sample_plan_complete') is True)
            e.check(test+'_all_samples_valid',all(v['passed'] for v in data['results'].values()))
            e.check(test+'_statistics_within_bounds',data.get('passed') is True and all(v['passed'] for v in data['statistics'].values()))
        e.attempt(test+'_summary',run)

def gate_timing_library_15pvt(e):
    all_points(e,lambda req,p,t:[f'driver_timing_{p}_{t}',f'receiver_timing_{p}_{t}'])
    def libraries():
        req=contract()[0]['requirements'];views=e.read(RELEASE/'views.json')
        for macro in MACROS:
            entries=views[macro]['liberty']
            e.check(macro+'_15_distinct_libraries',{(x['process'],x['temperature_c']) for x in entries}==set(points(req)) and len(entries)==15)
            good=True
            for entry in entries:
                text=(ROOT/entry['path']).read_text();e.files[entry['path']]=sha(ROOT/entry['path'])
                good&=sha(ROOT/entry['path'])==entry['sha256'] and text.count('{')==text.count('}') and f'cell ({macro})' in text
            e.check(macro+'_libraries_well_formed',good)
        reference=e.read(ROOT/'build/physical/io_ref/summary.json')
        e.check('libraries_read_by_sta',reference.get('passed') is True and reference.get('views_sha256')==sha(RELEASE/'views.json'))
    e.attempt('libraries_published',libraries)

def gate_published_views_integration(e):
    def run():
        policy=load(ROOT/POLICY);views=e.read(RELEASE/'views.json')
        for macro in policy['macros']:
            for view in policy['release_views']:
                item=views[macro][view];entries=item if isinstance(item,list) else [item]
                e.check(f'{macro}_{view}',bool(entries) and all(sha(ROOT/x['path'])==x['sha256'] for x in entries))
            e.check(macro+'_electrical_table_complete',views[macro]['electrical_tables'].get('complete') is True)
        reference=e.read(ROOT/'build/physical/io_ref/summary.json')
        e.check('reference_top_hardened_from_published_views',reference.get('passed') is True and reference.get('views_sha256')==sha(RELEASE/'views.json'))
        e.check('reference_top_signoff_metrics_zero',reference.get('signoff_failures')==[])
    e.attempt('views_and_reference_top',run)

def gate_fresh_joint_rc_and_release(e):
    def run():
        fresh=e.read(RELEASE/'fresh_rc.json');phys=physical();views=load(RELEASE/'views.json')
        for macro in MACROS:
            e.check(macro+'_published_gds_is_checked_gds',views[macro]['gds']['sha256']==phys[macro]['gds_sha256'])
            e.check(macro+'_published_netlist_is_checked_netlist',views[macro]['extracted_spice']['sha256']==phys[macro]['extraction']['netlist_sha256'])
            e.check(macro+'_fresh_extraction_reproduces_netlist',fresh[macro]['passed'] is True and fresh[macro]['gds_sha256']==phys[macro]['gds_sha256'] and
                sha(ROOT/fresh[macro]['fresh'])==fresh[macro]['fresh_sha256'] and sha(ROOT/fresh[macro]['checked'])==fresh[macro]['checked_sha256'] and
                netlists_equivalent(ROOT/fresh[macro]['checked'],ROOT/fresh[macro]['fresh'])['equivalent'])
    e.attempt('fresh_extraction',run)

GATES=dict(model_compatibility=gate_model_compatibility,numerical_refinement=gate_numerical_refinement,
    exact_rc_equivalence=gate_exact_rc_equivalence,native_drc_lvs_rc=gate_native_drc_lvs_rc,device_stress=gate_device_stress,
    analog_tx_rx_15pvt=gate_analog_tx_rx_15pvt,offset_and_mismatch=gate_offset_and_mismatch,async_link_eye=gate_async_link_eye,
    antenna_density_erc=gate_antenna_density_erc,timing_library_15pvt=gate_timing_library_15pvt,
    published_views_integration=gate_published_views_integration,fresh_joint_rc_and_release=gate_fresh_joint_rc_and_release)


def fresh_rc():
    """Re-extract the published GDS and record the netlist it yields (needs scripts/env.sh --tools)."""
    from extract import extract
    views=load(RELEASE/'views.json');layout=load(ROOT/'build/layout/current.json');result={}
    for macro in MACROS:
        gds=ROOT/views[macro]['gds']['path'];info=layout['designs'][macro]
        # The fresh run writes into the checked extraction's directory (same
        # GDS, same script), and Magic's output is not byte-reproducible. Every
        # bench is bound to the checked files, so set that directory aside and
        # put it back whatever happens.
        checked=ROOT/load(ROOT/'build/extracted/current.json')['designs'][macro]['raw_netlist']
        kept=RELEASE/'fresh_rc'/(macro+'.checked.rcx.spice');kept.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(checked,kept)
        aside=checked.parent.with_name(checked.parent.name+'.checked')
        if aside.exists():raise ValueError(f'Interrupted fresh extraction: restore {rel(aside)} to {rel(checked.parent)}')
        fresh=RELEASE/'fresh_rc'/(macro+'.fresh.rcx.spice')
        shutil.copytree(checked.parent,aside)
        try:
            summary=extract(macro,gds,layout['source_sha256'],info['ports'],info['lvs_source_sha256'])
            shutil.copyfile(ROOT/summary['raw_netlist'],fresh)
        finally:
            shutil.rmtree(checked.parent);aside.rename(checked.parent)
        if sha(checked)!=sha(kept):raise ValueError('Checked extraction was not restored')
        result[macro]=dict(passed=summary['passed'],gds_sha256=summary['gds_sha256'],checked=rel(kept),checked_sha256=sha(kept),
            fresh=rel(fresh),fresh_sha256=sha(fresh),comparison=netlists_equivalent(kept,fresh))
    (RELEASE/'fresh_rc.json').write_text(json.dumps(result,indent=2)+'\n')
    return 0 if all(v['passed'] for v in result.values()) else 1


def receipts():
    policy=load(ROOT/POLICY);binding=contract()[1]
    if set(policy['gates'])!=set(GATES):raise ValueError('Policy gates differ from the implemented judges')
    candidate=RELEASE/'candidate.json';candidate_hash=sha(candidate) if candidate.exists() else None
    folder=RELEASE/'receipts';folder.mkdir(parents=True,exist_ok=True);evidence={};report={}
    for gate in policy['gates']:
        e=Evidence()
        try:GATES[gate](e)
        except (OSError,ValueError,KeyError,TypeError,IndexError,json.JSONDecodeError) as error:
            e.checks['judge_completed']=False;e.notes['judge_completed']=str(error)
        passed=bool(candidate_hash and e.checks and e.files and all(e.checks.values()))
        receipt=dict(gate=gate,contract_sha256=binding,candidate_sha256=candidate_hash,state='pass' if passed else 'fail',
            complete=bool(e.checks and e.files),checks=e.checks,files=e.files,notes=e.notes,producer_sha256=sha(__file__))
        path=folder/(gate+'.json');path.write_text(json.dumps(receipt,indent=2)+'\n')
        evidence[gate]=dict(path=rel(path),sha256=sha(path))
        report[gate]=dict(state=receipt['state'],failed=[k for k,v in e.checks.items() if not v][:6],checks=len(e.checks))
    policy['evidence']=evidence
    (ROOT/POLICY).write_text(json.dumps(policy,indent=2)+'\n')
    print(json.dumps(report,indent=1))
    return 0 if all(v['state']=='pass' for v in report.values()) else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['publish','fresh-rc','receipts'])
    a=p.parse_args()
    return dict(publish=publish,receipts=receipts)[a.command]() if a.command!='fresh-rc' else fresh_rc()


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    sys.exit(main())
