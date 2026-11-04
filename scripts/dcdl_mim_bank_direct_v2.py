# SPDX-License-Identifier: GPL-3.0-only
"""Direct native delay-bank ports, retaining every coarse/fine delay device.

Remove only the two internal compound port buffers. The real upstream driver,
downstream load, edge slew, stress and multi-section propagation must be
characterized again. No production clock model is selected by this experiment.
"""
import dcdl_mim_bank_physical_v2 as base

native=base.native
COMPOUNDS=base.COMPOUNDS
VERSION='native-mim-bank-direct-ports-v2.1'


def name(coarse_count=16,fine_count=32):
    return base.name(coarse_count,fine_count).removesuffix('_physical_v2')+'_direct_v2'


def instances(coarse_count=16,fine_count=32):
    aliases=dict(f0='IN',r0='OUT')
    return [dict(c,pins={p:aliases.get(n,n) for p,n in c['pins'].items()})
            for c in base.instances(coarse_count,fine_count) if c['name'] not in ['input_buffer','output_buffer']]


def verilog(coarse_count=16,fine_count=32):
    cells=instances(coarse_count,fine_count);inputs=['IN',*native.controls(coarse_count,fine_count)]
    nets=sorted({n for c in cells for n in c['pins'].values()}-set(inputs)-{'OUT','VPWR','VGND'})
    text=('// SPDX-License-Identifier: GPL-3.0-only\n// Direct-port architecture experiment; fresh native qualification required.\n'
        '`default_nettype none\nmodule '+name(coarse_count,fine_count)+' (\n`ifdef USE_POWER_PINS\n    inout wire VPWR,VGND,\n`endif\n'
        '    input wire '+','.join(inputs)+',\n    output wire OUT\n);\n'
        '`ifndef USE_POWER_PINS\n    supply1 VPWR; supply0 VGND;\n`endif\n    wire '+','.join(nets)+';\n')
    for c in cells:
        text+='    (* keep="true", dont_touch="true" *) '+c['model']+' '+c['name']+' ('+','.join('.'+p+'('+n+')' for p,n in c['pins'].items())+');\n'
    return text+'endmodule\n`default_nettype wire\n'


def blackboxes():return base.blackboxes()
