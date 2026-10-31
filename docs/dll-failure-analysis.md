# OTA slow-corner acquisition failure

The completed `ota_w4_c8_loop_ss_0` architecture screen fails the original
1200–1500 ns scoring window. Simulation completes normally, clock cadence
passes, and the quarter-cycle delay stays inside 625 ± 100 ps. Feedback error
reaches 128.34 ps against 100 ps, and CTRL spans 87.89 mV against 20 mV.
This is the hybrid architecture bench: schematic controller plus captured
extracted PFD and delay line. It is not the new full-RC physical candidate.

## Measured cause

The waveform shows continued acquisition rather than a large oscillation:

| Interval (ns) | CTRL start/end (V) | CTRL slope (mV/ns) | Maximum feedback error (ps) |
| --- | --- | --- | --- |
| 1200–1300 | 1.3070 / 1.2757 | −0.315 | 128.34 |
| 1300–1400 | 1.2756 / 1.2465 | −0.291 | 121.40 |
| 1400–1500 | 1.2465 / 1.2200 | −0.266 | 114.08 |

The final 10 ns still have approximately 106.8 ps feedback error. After a
linear trend is removed separately from each 100 ns window, CTRL variation is
approximately 1.9 mV peak-to-peak. The scorer's `control_ripple_pp_mv` field
includes drift; the original 87.89 mV value is correct as total variation but
does not establish an 88 mV oscillation. CTRL remains away from the rails and
continues moving in the direction that improves the phase error. This trace
does not establish eventual convergence or phase margin.

The immediate mechanism is limited correction current into the 8 pF nominal
integrator during a long control-voltage excursion. In the scoring window,
UF−DF averages −55 to −46 mV. The standalone SS/0 °C OTA characterization
measures approximately 44 µS transconductance around this operating range.
That input produces correction current on the order of a few microamps.
Using the nominal capacitor alone, the measured slope corresponds to about
2.1–2.5 µA. This is a consistency estimate: parasitic capacitance, signal
nonlinearity and output conductance are not included in that simple equation.

The slow corner starts closer in phase at the 1.8 V precharge setting, but still
needs substantial CTRL movement. Its smaller sustained detector error gives
weaker OTA drive. TT/FF begin with larger errors and larger correction drive;
they reach the steep part of the delay-control characteristic and settle by
the scoring window. The SS trace's improving error versus CTRL also indicates
relatively low delay sensitivity along the early part of its trajectory.
This explanation is inferred from the measured trajectories, not from a
complete loop-gain extraction. A collapsed OTA gm is not supported by the
standalone characterization.

## Comparisons and remaining checks

The same-corner repaired CP passes: 20.15 ps feedback error, 21.81 mV control-copy
error and 6.43 mV CTRL variation. Its control is already near its final value
by approximately 300 ns. This demonstrates a workable operating point in that
screening delay line; it does not qualify the CP across the full matrix.

The ongoing alternatives also show faster acquisition at a common 450–500 ns
window. Their mean CTRL values are 1.5931 V for W4/C8, 1.4655 V for W4/C4,
and 1.5404 V for W8/C8, all at SS/0 °C. These partial comparisons support
reducing the capacitor or increasing OTA input width. They do not establish
passing settled results. The existing W4/C4 and W8/C8 runs should finish before
selecting the repair. A later extended-duration W4/C8 diagnostic could test
eventual convergence, while preserving its failure of the original 1500 ns
test and the original limits.

The earlier OTA component offset failures are a separate issue. At SS/0 °C,
common mode 0.6 V, equivalent input offset grows from 8.08 mV at CTRL 1.1 V
to 11.68 mV at 1.3 V and 13.63 mV at 1.4 V. Its dependence on output voltage
is consistent with finite output resistance and unequal drain voltages in the
current mirrors. This is a systematic-model effect, not measured mismatch.
The offset must be included in the final phase-error budget; it is not by
itself evidence of the slow acquisition mechanism or of instability.

A low BAD signal during the scoring window is compatible with the failure:
the monitor must assert for offsets of at least 150 ps, whereas the loop's
feedback-error requirement is tighter at 100 ps.

Raw input and recomputed interval measurements are retained in
`build/diagnostics/dll_failure_analysis/results.json`, with waveform hashes.
The analysis producer is `build/diagnostics/dll_failure_analysis/analyze.py`.
No circuit, simulator, pass threshold or queued producer was changed.


## Native W8/C4 monitor timing, 2026-10-31

The exact physical candidate `0f0c41cbc75c` passes SS/0 °C 0/+50 ps but misses
both ±150 ps faults through 160 ns. The ±300 ps cases eventually assert BAD,
but fail the unchanged requirement for valid fault coverage across the
120–160 ns window. Reanalysis of their completed waveforms finds:

| Offset | BAD falls after startup | BAD next rises | Filtered UF−DF mean, 120–160 ns |
| --- | --- | --- | --- |
| +150 ps | 80.552 ns | none through 160 ns | +89.34 mV |
| −150 ps | 80.190 ns | none through 160 ns | −91.80 mV |
| +300 ps | 79.421 ns | 147.595 ns | +160.83 mV |
| −300 ps | 79.019 ns | 137.510 ns | −158.93 mV |

TT/25 °C +150 ps also stays quiet after 89.361 ns despite a 90.71 mV filtered
difference. The startup high is not evidence of sustained fault detection.
`monitor_fault_timing_diagnosis.json` under qualification `d4d687cf4e0b5e1e`
binds these crossing measurements to the completed waveform and report hashes.

These failures justify measuring the divider and comparator nodes rather than
changing the fault window. A loaded/unloaded schematic control and a stronger
monitor are being compared with captured coupling capacitances. The repair's
new GDS passes DRC/LVS/extraction/audit, but its electrical response has not yet
been established. The old coordinator is draining submitted work without new
dispatch; the RX characterization remains intact.


The loaded-baseline SS/0 °C +150 ps control now reproduces the missed fault:
BAD stays below 4.5 µV in 120–160 ns while UF−DF averages 89.51 mV. Its
comparator O rises from about 0.55 V at 120 ns to 0.69 V at 160 ns without
asserting POS. This makes captured capacitance a demonstrated contributor;
it does not exclude further native resistance or junction effects.

With monitor resistor lengths divided by four, averaging capacitance multiplied
by four and comparator branch widths multiplied by four, the same loaded
+150 ps test passes. BAD reasserts at 88.271 ns and stays near 1.8 V throughout
the original scoring window. Comparator O averages 1.127 V instead of 0.643 V.
The repaired filtered difference is 85.86 mV. This is one proxy condition,
not native signoff: quiet ±50 ps, both fault polarities, the remaining corners,
source-specific loop screening and fresh extracted qualification remain required.
