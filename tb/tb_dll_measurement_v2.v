// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Composition test: real sequencer, phase controller, launch CDC and event
// guards. Only external physical paths/arbiter are synthetic timing models.
module tb_dll_measurement_v2;
    parameter ADMITTED=1;
    reg clk=0,raw=0,reset_n=1,request=0,separated=1;
    always #20 clk=~clk;
    always #1.25 raw=~raw;
    wire valid,epoch_ok,detector_ok,balanced,short_period,long_period;
    wire [1:0] fastest,section_a,section_b;
    wire [3:0] failure;
    wire period_mode,swap,positive,arm,launch,reference;
    wire [15:0] route_sequence;
    always @(posedge dut.trial.result_valid)if(dut.trial.failure_code)
        $display("Rejected physical trial reason=%d at=%t seen=%b duplicate=%b levels=%b event_reset=%b",dut.trial.failure_code,$realtime,dut.trial.seen_sync,dut.trial.duplicate_sync,dut.trial.level_sync,dut.trial.event_reset_n);
    reg [15:0] applied_sequence=0;
    reg a=0,b=0,qa=1,qb=1;
    integer delays[0:3];
    integer total,k,launches=0;
    real delay_a,delay_b;
    always @(negedge clk)applied_sequence<=route_sequence;
    openlvds_dll_measurement_v2 #(.MODEL_ADMITTED(ADMITTED)) dut(
        .mgmt_clk_25(clk),.raw_reference(raw),.reset_n(reset_n),.enable(1'b1),.clock_present(1'b1),
        .frontend_ready(1'b1),.measure_request(request),.separated_mode(separated),.measure_valid(valid),
        .measure_epoch_valid(epoch_ok),.measure_detector_valid(detector_ok),.measure_balanced(balanced),
        .measure_fastest(fastest),.measure_period_short(short_period),.measure_period_long(long_period),
        .failure_code(failure),.route_next_period(period_mode),.route_swap(swap),.route_positive_offset(positive),
        .route_section_a(section_a),.route_section_b(section_b),.route_sequence(route_sequence),
        .routes_applied(1'b1),.routes_sequence(applied_sequence),.arm(arm),.launch_pulse(launch),
        .reference_pulse(reference),.observed_a(a),.observed_b(b),.qa(qa),.qb(qb)
    );
    always @(launch)begin
        total=0;for(k=0;k<4;k=k+1)total=total+delays[k];
        delay_a=1.0+delays[section_a]/1000.0+(positive ? 0 : 0.02);
        delay_b=1.0+(period_mode ? total : delays[section_b])/1000.0+(positive ? 0.02 : 0);
        if(!period_mode)a<=#(delay_a)launch;
        b<=#(delay_b)launch;
    end
    always @(reference)if(period_mode)a<=#(1.0+(positive ? 0 : 0.02))reference;
    always @(negedge arm)begin qa=1;qb=1;end
    always @(posedge a)if(arm && qa && qb)begin qa=swap ? 1 : 0;qb=swap ? 0 : 1;end
    always @(posedge b)if(arm && qa && qb)begin qa=swap ? 0 : 1;qb=swap ? 1 : 0;end
    reg [22:0] held_route;
    always @(posedge arm)held_route={route_sequence,period_mode,swap,positive,section_a,section_b};
    always @(posedge clk)if(arm && held_route!={route_sequence,period_mode,swap,positive,section_a,section_b})
        $fatal(1,"Physical route changed while detector was armed");
    always @(posedge launch)begin
        launches=launches+1;
        if(!arm || applied_sequence!=route_sequence)$fatal(1,"Unapplied route launched");
    end
    task measure;
        input separate,expected_balanced,expected_short,expected_long;
        integer before_count;
        begin
            @(negedge clk);request=0;repeat(3)@(negedge clk);
            before_count=launches;separated=separate;request=1;
            wait(valid);#0.001;
            if(ADMITTED)begin
                if(failure || !epoch_ok || !detector_ok || balanced!=expected_balanced ||
                   short_period!=expected_short || long_period!=expected_long)
                    $fatal(1,"Composed measurement incorrect reason=%d balanced=%b short=%b long=%b seen=%b duplicate=%b levels=%b a=%b b=%b",failure,balanced,short_period,long_period,dut.trial.seen_sync,dut.trial.duplicate_sync,dut.trial.level_sync,a,b);
                if(launches-before_count!=(separate ? 72 : 12))$fatal(1,"Wrong actual isolated pulse count %d",launches-before_count);
            end else if(failure!=8 || launches!=0 || epoch_ok || detector_ok)$fatal(1,"Unadmitted physical interface emitted evidence");
            @(negedge clk);request=0;repeat(3)@(negedge clk);
        end
    endtask
    initial begin
        for(k=0;k<4;k=k+1)delays[k]=625;
        #0.001;reset_n=0;#10;reset_n=1;
        measure(1,1,0,0);
        if(ADMITTED)begin
            measure(0,0,0,0);
            for(k=0;k<4;k=k+1)delays[k]=600;
            measure(0,0,1,0);
            for(k=0;k<4;k=k+1)delays[k]=1250;
            measure(0,0,0,1);
        end
        $display("PASS v2 composed measurement emits actual isolated tags and next-epoch period brackets");$finish;
    end
    initial begin #1000000;$fatal(1,"Composed measurement watchdog seq=%d trial=%d",dut.sequence_control.state,dut.trial.state);end
endmodule
