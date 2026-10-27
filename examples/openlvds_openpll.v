// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Build with IntegerPLL_25MHzModeConfig_modern.v, never both mode tables.
// TRACKING indicates the configured control state, not a measured lock result.
module openlvds_openpll (
    input wire ref_25, input wire reset_n, input wire enable,
    output wire clk_400, output wire pll_tracking, output wire config_valid
);
    IntegerPLL_HardMacroTop_EINVP_25MHzConfigured pll (
        .REF(ref_25), .RESET_N(reset_n), .PLL_ENABLE(enable),
        .FEEDBACK_DIVIDER(5'd16), .PLLOUT(clk_400),
        .TRACKING(pll_tracking), .CONFIG_VALID(config_valid)
    );
endmodule
`default_nettype wire
