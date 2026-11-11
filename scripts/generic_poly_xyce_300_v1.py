# SPDX-License-Identifier: GPL-3.0-only
"""Isolated generic-poly adapter candidate; admission requires native comparisons.

PDK model: RSH=rp1, DW=-(tol_poly+poly_dw)/2, TNOM=30,
TC1R=tc1rsgpu, TC2R=tc2rsgpu. ngspice narrows width only. Geometry
is passed in microns and the PDK DW is in meters. Xyce ignores TC1R/TC2R/DW;
its NARROW also shortens length, so alias substitution is insufficient.
No PDK file is changed. Noise/statistical qualification is outside this pilot.
"""
NAME='openlvds_res_generic_po_compat_300_v1'
MODEL='''* Generic poly compatibility candidate, fixed PDK equation and units.
.subckt openlvds_res_generic_po_compat_300_v1 t1 t2 w=1 l=1
R0 t1 t2 R={rp1*(l*1e-6)/(w*1e-6+(tol_poly+poly_dw)/2)*(1+tc1rsgpu*(temper-30)+tc2rsgpu*(temper-30)*(temper-30))}
.ends openlvds_res_generic_po_compat_300_v1
'''
