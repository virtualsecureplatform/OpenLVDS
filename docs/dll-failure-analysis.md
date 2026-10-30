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
