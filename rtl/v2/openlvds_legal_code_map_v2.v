// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Constant legal-index -> native raw-code ROM. Entry zero occupies the low
// RAW_WIDTH bits of RAW_CODES. A table certificate is an external requirement;
// MODEL_ADMITTED remains zero for all development/proposed tables.
module openlvds_legal_code_map_v2 #(
    parameter INDEX_WIDTH=13,RAW_WIDTH=13,CODE_COUNT=2,NATIVE_CODE_COUNT=8192,
    parameter MODEL_ADMITTED=0,
    parameter [CODE_COUNT*RAW_WIDTH-1:0] RAW_CODES=0
)(
    input wire [INDEX_WIDTH-1:0] index,
    output wire [RAW_WIDTH-1:0] raw_code,
    output wire valid
);
    localparam PARAMETERS_VALID=INDEX_WIDTH>=1 && INDEX_WIDTH<=16 && RAW_WIDTH>=1 && RAW_WIDTH<=16 &&
        CODE_COUNT>=2 && CODE_COUNT<=(2**INDEX_WIDTH) &&
        NATIVE_CODE_COUNT>=2 && NATIVE_CODE_COUNT<=(2**RAW_WIDTH);
    function [RAW_WIDTH:0] lookup;
        input [INDEX_WIDTH-1:0] legal_index;
        reg [RAW_WIDTH-1:0] selected;
        begin
            lookup=0;
            selected=RAW_CODES[legal_index*RAW_WIDTH +: RAW_WIDTH];
            if(PARAMETERS_VALID && MODEL_ADMITTED && legal_index<CODE_COUNT && selected<NATIVE_CODE_COUNT)
                lookup={1'b1,selected};
        end
    endfunction
    // A continuous function also drives constant-disabled configurations at
    // time zero; a parameter-folded always @* may have no sensitivity events.
    assign {valid,raw_code}=lookup(index);
endmodule

// All four committed DLL indices share one immutable common table. Invalid
// lookup in any section invalidates the complete configuration, never one lane.
module openlvds_dll_code_map_v2 #(
    parameter INDEX_WIDTH=13,RAW_WIDTH=13,CODE_COUNT=2,NATIVE_CODE_COUNT=8192,
    parameter MODEL_ADMITTED=0,
    parameter [CODE_COUNT*RAW_WIDTH-1:0] RAW_CODES=0
)(
    input wire [4*INDEX_WIDTH-1:0] indices,
    output wire [4*RAW_WIDTH-1:0] raw_codes,
    output wire valid
);
    wire [3:0] lane_valid;
    wire [4*RAW_WIDTH-1:0] mapped;
    genvar k;
    generate for(k=0;k<4;k=k+1)begin:section
        openlvds_legal_code_map_v2 #(.INDEX_WIDTH(INDEX_WIDTH),.RAW_WIDTH(RAW_WIDTH),.CODE_COUNT(CODE_COUNT),
            .NATIVE_CODE_COUNT(NATIVE_CODE_COUNT),.MODEL_ADMITTED(MODEL_ADMITTED),.RAW_CODES(RAW_CODES)) lookup(
            .index(indices[k*INDEX_WIDTH +: INDEX_WIDTH]),.raw_code(mapped[k*RAW_WIDTH +: RAW_WIDTH]),.valid(lane_valid[k]));
    end endgenerate
    assign valid=&lane_valid;
    assign raw_codes=valid ? mapped : {4*RAW_WIDTH{1'b0}};
endmodule
`default_nettype wire
