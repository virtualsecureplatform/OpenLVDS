// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_legal_code_map_v2;
    reg [1:0] index=0;
    wire [3:0] native,unadmitted,bad_native,bad_shape;
    wire valid,unadmitted_valid,bad_native_valid,bad_shape_valid;
    openlvds_legal_code_map_v2 #(.INDEX_WIDTH(2),.RAW_WIDTH(4),.CODE_COUNT(3),.NATIVE_CODE_COUNT(10),
        .MODEL_ADMITTED(1),.RAW_CODES(12'h925)) good(index,native,valid);
    openlvds_legal_code_map_v2 #(.INDEX_WIDTH(2),.RAW_WIDTH(4),.CODE_COUNT(3),.NATIVE_CODE_COUNT(10),
        .MODEL_ADMITTED(0),.RAW_CODES(12'h925)) unqualified(index,unadmitted,unadmitted_valid);
    openlvds_legal_code_map_v2 #(.INDEX_WIDTH(2),.RAW_WIDTH(4),.CODE_COUNT(3),.NATIVE_CODE_COUNT(10),
        .MODEL_ADMITTED(1),.RAW_CODES(12'hfff)) outside_native(index,bad_native,bad_native_valid);
    openlvds_legal_code_map_v2 #(.INDEX_WIDTH(2),.RAW_WIDTH(4),.CODE_COUNT(5),.NATIVE_CODE_COUNT(10),
        .MODEL_ADMITTED(1),.RAW_CODES(20'h12345)) invalid_shape(index,bad_shape,bad_shape_valid);
    reg [7:0] indices=8'b10_01_00_10;
    wire [15:0] mapped;
    wire all_valid;
    openlvds_dll_code_map_v2 #(.INDEX_WIDTH(2),.RAW_WIDTH(4),.CODE_COUNT(3),.NATIVE_CODE_COUNT(10),
        .MODEL_ADMITTED(1),.RAW_CODES(12'h925)) four(indices,mapped,all_valid);
    integer k;
    initial begin
        #1;if(native!==5 || !valid)$fatal(1,"Entry zero must use low packed bits");
        index=1;#1;if(native!==2 || !valid)$fatal(1,"Filtered raw code mapping lost");
        index=2;#1;if(native!==9 || !valid)$fatal(1,"Last legal entry lost");
        index=3;#1;if(native!==0 || valid)$fatal(1,"Out-of-range legal index escaped");
        index=2'bxx;#1;if(native!==0 || valid)$fatal(1,"Unknown index escaped");
        for(k=0;k<3;k=k+1)begin
            index=k;#1;
            if(unadmitted!==0 || unadmitted_valid || bad_native!==0 || bad_native_valid || bad_shape!==0 || bad_shape_valid)
                $fatal(1,"Invalid/unadmitted ROM escaped");
        end
        if(!all_valid || mapped!==16'h9259)$fatal(1,"Four-section mapping was torn");
        indices[3:2]=3;#1;
        if(all_valid || mapped!==0)$fatal(1,"One invalid lane must invalidate all native codes");
        $display("PASS mapped native ROM bounds, admission, packed order and atomic four-section validity");$finish;
    end
endmodule
