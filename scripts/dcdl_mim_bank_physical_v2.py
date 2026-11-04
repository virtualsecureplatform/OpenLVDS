# SPDX-License-Identifier: GPL-3.0-only
"""Single-driver physical view of the retained native parallel-gate bank.

Identical native gates sharing an output require an actual compound macro.
The logical interface alone supplies no physical/timing certificate; assembly
must require GDS, LVS and RC proofs for all four compound macro types.
"""
import dcdl_mim_bank_v2 as native

VERSION='balanced-mim-bank-compound-macro-view-v2.1'
COMPOUNDS={native.SC+n:'openlvds_'+n+'_pair_v2' for n in ['buf_4','nand2_4','nand2_8','nand2b_4']}
SIGNALS={native.SC+'buf_4':(['A'],'X'),native.SC+'nand2_4':(['A','B'],'Y'),
         native.SC+'nand2_8':(['A','B'],'Y'),native.SC+'nand2b_4':(['A_N','B'],'Y')}


def name(coarse_count=16,fine_count=32):return native.name(coarse_count,fine_count).removesuffix('_v2')+'_physical_v2'


def instances(coarse_count=16,fine_count=32):
    cells=native.instances(coarse_count,fine_count);by_name={c['name']:c for c in cells};result=[]
    for cell in cells:
        if cell['name'].endswith('_1'):continue
        if cell['name'].endswith('_0'):
            partner=by_name.get(cell['name'][:-2]+'_1')
            if partner is None or (cell['model'],cell['pins'])!=(partner['model'],partner['pins']):
                raise ValueError('Compound drivers must have identical native models and inputs')
            result.append(dict(name=cell['name'][:-2],model=COMPOUNDS[cell['model']],
                pins=dict(cell['pins'],VPWR='VPWR',VGND='VGND')))
        else:result.append(cell)
    return result


def verilog(coarse_count=16,fine_count=32):
    cells=instances(coarse_count,fine_count);inputs=['IN',*native.controls(coarse_count,fine_count)]
    nets=sorted({n for c in cells for n in c['pins'].values()}-set(inputs)-{'OUT','VPWR','VGND'})
    text=('// SPDX-License-Identifier: GPL-3.0-only\n// Compound macro GDS/LVS/RC is mandatory; interfaces are not timing models.\n'
        '`default_nettype none\nmodule '+name(coarse_count,fine_count)+' (\n`ifdef USE_POWER_PINS\n    inout wire VPWR,VGND,\n`endif\n'
        '    input wire '+','.join(inputs)+',\n    output wire OUT\n);\n'
        '`ifndef USE_POWER_PINS\n    supply1 VPWR; supply0 VGND;\n`endif\n    wire '+','.join(nets)+';\n')
    for c in cells:text+='    (* keep="true", dont_touch="true" *) '+c['model']+' '+c['name']+' ('+','.join('.'+p+'('+n+')' for p,n in c['pins'].items())+');\n'
    return text+'endmodule\n`default_nettype wire\n'


def blackboxes():
    text=native.blackboxes().removesuffix('`default_nettype wire\n')
    for model,macro in COMPOUNDS.items():
        inputs,output=SIGNALS[model]
        text+='(* blackbox *) module '+macro+'(input wire '+','.join(inputs)+',output wire '+output+',inout wire VPWR,VGND);endmodule\n'
    return text+'`default_nettype wire\n'
