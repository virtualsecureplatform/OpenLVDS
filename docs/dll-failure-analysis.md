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


The matched unloaded +150 ps control passes, with BAD rising at 28.794 ns and
comparator O averaging 1.505 V. Its loaded counterpart has a similar filtered
error (89.51 versus 90.03 mV) but O averages 0.643 V and BAD never reasserts.
The repaired loaded case restores a passing response at 88.271 ns. These controls
hold the PFD/bias and analog device definitions constant while adding the captured
capacitance, establishing a causal loading effect within the proxy.

The +300 ps loaded control instead passes its reference-cycle scoring, with BAD
rising at 121.023 ns, versus 22.119 ns unloaded. The original native result remains
a failure at 147.595 ns. The missing distributed resistance and extracted device
junction geometry remain candidates for the remaining timing difference; they
have not been isolated. The negative-control expectation is preserved as a
mismatch. Full native qualification remains necessary.


## Repaired physical monitor: native failure

Qualification `0cc06862af2fae63`, case `phase_ss_0_150ps`, completes normally
but fails electrically. BAD falls at 52.100 ns and never reasserts through
160 ns; its maximum during 120–160 ns is 7.655 µV. Filtered UF−DF averages
85.287 mV versus 85.863 mV for the passing repaired loaded proxy. The full-RC
waveform SHA-256 is
`81089b51decf8029d1a0ff80fada0243db8840a4a3b1a775ebf563d748f9d232`.

The repair therefore has not solved the physical failure. Its positive comparator
output has 396.3 fF incident extracted external capacitance, compared with
222.7 fF in the proxy's old layout. Native junction geometry and distributed
resistance are also absent from that proxy. These remain possible explanations,
not isolated causes.

The next diagnostic probes every actual PA/PB and comparator O/OB/L/T terminal,
the positive tail's PC gate and local VDDD contacts. A separate native DC
diagnostic adds three test ports to clamp UF/DF/CTRL to the measured fault-case
means without replacing any extracted device or R/C. A high DC BAD with a
failed transient would support a settling problem; a low DC BAD requires
examining comparator input difference, gain, bias and readout headroom first.
Neither result changes the original phase test or releases the candidate.


The clamped native DC diagnostic `monitor_native/0fcf74f7d7868e78/dc` completes
with BAD = 1.800000 V and POS = 1.799995 V. PA/PB are 0.381484/0.372850 V
(8.634 mV difference), comparator O = 1.456808 V, L = 0.711481 V, and
T = 1.562139 V. The local positive-tail VDDD terminals span
1.799555–1.800000 V and PC = 0.612602 V. This shows that the native comparator
can detect the measured positive fault at equilibrium. It supports a dynamic
settling explanation; it does not prove which capacitance or resistance dominates,
or establish the response with pulsed inputs. The waveform and native library
hashes are retained in that diagnostic's manifest and summary.

A source-identical local comparator layout passes DRC/LVS. Keeping O/OB/L/T
inside small comparator islands avoids their long drops through the passive
bank. Its extracted capacitance and native response must improve before this
physical change is selected. The failed 160 ns trace remains unchanged.


The first local layout reduces O/OB/L/T incident external capacitances to
93.272/41.225/94.846/143.083 fF, from 396.255/199.656/339.985/570.225 fF.
Its long child-port escapes instead increase PA/PB and activity-reference
loading. `monitor_capacitance_comparison.json` under layout `0a4253d72e392de9`
records both netlist/GDS hashes and the node sums. A fresh local-port variant
passes DRC/LVS and is being extracted before native selection. No transient
improvement has yet been demonstrated by either layout.


## Source-specific acquisition failure

The new source-specific SS/0 °C screen completes 1500 ns but settles at the
high CTRL rail instead of lock: CTRL = 1.783719 V, feedback error = 845.001 ps,
quarter delay about 223.6 ps, UF−DF = +159.381 mV, and BAD high. At 90–120 ns
CTRL already averages 1.782274 V and stays near that value. This is not merely
a late monitor assertion or a small CTRL-ripple failure.

At 1200 ns, PH0 rises at 1200.087699 ns, PH180 at 1200.521840 ns and PD_REF
at 1201.366732 ns. Thus the PFD feedback edge precedes its reference by about
845 ps, while raw UP/DN means across 1200–1500 ns are 0.886011/0.690257 V.
The positive area imbalance drives the OTA toward higher CTRL, rather than
correcting this leading-feedback condition. This makes wide-range detector
capture/reset timing a priority for diagnosis; a reduced precharge voltage is
another experiment, not an established fix. Matched ±850 ps input controls and
a reset coincidence taken before the UP/DN output buffers can test that hypothesis.

The old passing W8/C4 screen is not a matched control: it retains an extracted
standalone delay line and the preceding captured PFD, while the new screen uses
fully native-finger schematic analog/delay devices and the 8-port PFD. Common
non-monitor analog device rows are unchanged, but the delay implementation and
PFD view differ. Do not attribute the new failure solely to monitor scaling or
reuse the old success as qualification of the repaired source. The completed
new summary binds waveform
`dbb036ab1be26613944e759c5e7aa7a1918f96d0b6b73ddc5d77eb9653bc0874`
and raw trace
`045ef5b90e21ca5fe7b2aae9bb88e88c8c96d106f8407d7ab2fa8e52a26025ca`.


The native internal-node transient now completes and reproduces the original
phase metrics exactly. In 120–160 ns PA/PB average 0.381463/0.370171 V
(+11.292 mV input difference), but comparator O averages only 0.640525 V
and spans 0.566044–0.694506 V. POS stays low and BAD never reasserts.
Comparator L/T average 0.707203/1.558706 V, PC 0.612662 V, and local VDDD
1.799777 V; LOW/HIGH remain near zero. Comparing these measurements with the
DC solution supports slow positive-comparator output settling despite a valid
input margin, rather than a missing input difference or collapsed bias/supply.
The report is `monitor_native/0fcf74f7d7868e78/transient/summary.json`.

`diagnose_pfd_capture.py` separately prepares matched SS/0 °C controls at
−850, +850 and 0 ps. It compares the captured exact-RC PFD with PDK transistor
cell schematics, then changes only the schematic coincidence inputs from
buffered UP/DN to the internal flip-flop Q outputs. All views retain the same
native-finger schematic analog loading and extracted bias. Measurements use
raw UP/DN area during 60–80 ns; the filters need not have reached equilibrium.
These controls diagnose capture sign and reset feedback, not monitor fault
timing or PHY qualification. The Q-reset view has no new physical implementation.


## First passing native physical monitor repair

The source-identical local-port layout passes the native SS/0 °C +150 ps test
in qualification `c47b7dc98d92327b`. BAD reasserts at 54.618696 ns after its
26.274737 ns startup fall and remains at 1.8 V in the unchanged scoring window.
Filtered difference is 85.641 mV versus 85.287 mV for the failed preceding
physical layout. Combined with normal native input/bias voltages, a high DC
output and much lower O capacitance, this establishes a working physical
settling repair at this condition. Quiet behavior, the opposite polarity, other
PVT and acquisition remain unqualified.

The −850 ps native-RC PFD control also completes and reproduces the wrong
correction sign without feedback: UP−DN = +261.069 mV. Each input contributes
eight rising edges in 60–80 ns, compared with five UP and six DN rising edges.
UP high time reaches 2.858485 ns, longer than the 2.5 ns clock period. Missed
input cycles during the reset sequence are therefore a supported explanation
for the pulse-area sign error. The source-bound `cycle_diagnosis.json` under
`pfd_capture/b65a8cceadd819c0/native_rc_output_reset_-850ps` records crossings,
complete pulse widths and waveform/report hashes. These results justify the
matched reset-tap comparison; they do not yet prove an internal-Q reset fixes
physical capture, near-zero activity indication or closed-loop acquisition.


## Matched schematic capture controls and physical Q-reset experiment

At −850 ps the PDK transistor schematic with buffered-output reset gives
UP−DN = −617.441 mV; the same schematic with internal-Q reset gives
−612.378 mV. Both signs are correct, unlike the native extracted PFD's
+261.069 mV. Thus the schematic control does not reproduce the failure. Its
Q-reset result establishes neither causality for the native fault nor a physical
repair. Extracted routing/device parasitics must be included in the next test.

`sky130/experiments/lvds_pfd_area_qreset.v` changes only the coincidence inputs
from UP/DN to the corresponding flip-flop Q outputs. The public eight-terminal
interface and buf_8 output drivers are retained. `pfd_qreset_policy.py` requires
this topology plus direct clocks, high-tied data, the original enable/reset
connections, separate output buffers and absence of clock-delay cells. It
rejects the preceding buffered-reset topology, and the preceding policy rejects
the new topology. Neither policy is silently broadened.

`pfd_qreset_physical_v1` passes the physical flow, zero-error Magic/KLayout DRC,
zero LVS device/net/property/pin differences and the new structural check.
`preceding_policy_check.json` preserves the unchanged hardener's expected
interface rejection. The accepted summary explicitly names `pulse-area-q-reset`
and archives the producer files; it is not registered as the active PFD.
Extraction/audit and matched native capture tests are pending.


The physical internal-Q-reset candidate's −850 ps probe fails too:
UP/DN = 0.815017/0.554276 V, raw difference +260.742 mV and filtered
UF/DF = 0.687823/0.529048 V. Moving coincidence before buf_8 alone is
insufficient. Its retained report is
`pfd_physical_capture/390d2193239c4bbe/-850/summary.json`; waveform SHA-256
is `3868e5fb79b7e5cd56a70c70786f6cd2e85b6361cf581b625eea96a4638e18b4`.

The next hardware experiment shortens the reset logic itself to one AOI gate.
With disallow = NAND(RESET_N, PD_ENABLE), an a22oi_4 cell with B2 tied high
implements clear_b = NOT((raw_up AND raw_dn) OR disallow). The raw-Q reset
path crosses one cell instead of the coincidence AND and following clear gate.
The enable/reset truth table and separate buf_8 output paths remain required
by `pfd_fast_reset_policy.py`. This is a timing hypothesis; new physical capture,
quiet/activity and closed-loop tests are still needed.


The actual single-AOI PFD now corrects the tested −850 ps sign error: native
UP−DN = −636.215 mV, versus +260.742 mV for the internal-Q-only variant and
+261.069 mV for the preceding buffered-reset variant. This supports shortening
the reset logic as a working capture repair at this condition. Complementary
polarity, quiet behavior, capture range, PVT and acquisition remain unproven.
The matching source-specific loop screen is prepared and gated on the remaining
native controls; no scoring window or phase limit has changed.


## Completed receiver aperture failures, 2026-10-31

The frozen full-RC RX campaign `rx_aperture/e9ca7d2f2ae6d61b` completes all
480 conditions: 356 boundaries pass and 124 fail to bracket. The read-only
`diagnose_rx_aperture.py` rechecks all 248 failed-condition endpoint waveforms
through the original witness checker, including hashes, fixed supply, PVT,
stimulus and original public-output observation window. Diagnostic receipt:
`build/diagnostics/rx_aperture_failure/85a2639a36dfe760/summary.json`.

Every failed condition has failing −800 and +800 ps endpoints. At every +800 ps
endpoint VALID passes while at least one data output violates the original
0.36/1.44 V logic limits. Failures group as 72 SS, 36 SF and 16 TT conditions;
the TT failures all use 200 ps clock slew. This is an observed output-level
failure at ample nominal stimulus separation, not evidence that a wider search
bracket alone would fix characterization. It does not yet isolate the internal
sampling, publication delay, output drive or extracted RC contribution.

For TT/0 °C, rising data/rising clock, 200/20 ps clock/data slew, setup +800 ps,
the two expected-high public outputs have minima of 1.4367 and 1.4316 V. For SS/0 °C,
20/20 ps slew and the same edge/polarity/setup, they range 0.7231–1.3389 V and
0.7147–1.3328 V. VALID remains high in both examples. The original pass windows
and limits remain unchanged, and the failed table cannot qualify link timing.

The next isolated RX controls should use these two fixtures plus a passing FF
control: compare native public-port waveforms with native internal publication
and sampler outputs, then compare a retained stronger public output buffer
under the same 20 fF load. Any buffered variant needs separate hardening,
extraction and RC audit; passing selected controls would precede a fresh full
480-condition table. Sampling or clock-buffer changes should follow only if
internal waveforms establish an upstream fault. No RX circuit repair is claimed
from the endpoint diagnosis.


Reanalysis of the original +800 ps public traces identifies a delayed rising
transition in these examples. SS/0 °C Q0/Q1 reach 1.44 V about 1.11 ns after
publication; TT/0 °C with 200 ps clock slew reaches it about 0.80 ns after
publication, just after the required window begins. The passing FF control
reaches it about 0.61 ns after publication. At SS, Q0 rises from 0.723 V at
+0.80 ns to 1.339 V at +1.05 ns and 1.508 V at +1.15 ns. These are slow
published transitions, rather than demonstrated rail collapse or a persistent
wrong bit in those examples. The original window still fails.

Source hashes, unchanged witness reanalysis, sampled profiles and interpolated
1.44 V crossing times are captured in
`build/diagnostics/rx_aperture_failure/publication_transition_timing.json`;
producer `build/diagnostics/resident_jobs/rx_publication_timing.py`.
The routed design uses `buf_1` at both public data outputs. Their extracted
incident external capacitances are about 2.81/2.80 fF before the separate 20 fF
fixture loads (coupling-inclusive sums, excluding native junction capacitance).
The queued internal-stage and zero-external-load controls will distinguish
output loading from delay already present in the flop/publication path.


The first native internal control reproduces all SS +800 ps baseline public
limits exactly. During the observation window, data[0]'s publication flop Q is
1.79989–1.80001 V, the final buffer gates are 1.30–1.73 mV, and its local PFET
supply is 1.7772–1.7833 V. Thus the final-stage input is already established
while its public output still charges. The matched zero-external-data-load
control passes, with Q0/Q1 minima 1.79890/1.79842 V. Original 20 fF loading
fails with minima 0.72308/0.71469 V. Both records are under
`rx_publication/dd89f11b1af99f29`; all other stimulus, original scoring and
VALID loading are preserved. This establishes external data loading as a cause
for this SS failure and motivates stronger public drivers, while preserving
the original timing/level requirements and the full-RC test requirement.


## Loaded native buffered RX repair evidence

The audited `buf_4` candidate passes the previously failed SS/0 °C rising-data
+800 ps setup endpoint with the original 20 fF loads and original observation
window: public Q0/Q1 minima improve from 0.72308/0.71469 V to
1.67781/1.63361 V. The falling-data control passes with maxima
0.26292/0.33213 V, below the unchanged 0.36 V low-level limit. Both preserve
valid publication, stimulus separation and the actual native extracted network.
Their waveform hashes are
`329480d28d4bd690ac5e78f6347bd3f4b6d4c89fd3a4f8b714cdc017c41e359d`
and `1df929d81345dd1a571613fce069b88bd4ee7bbd92f122917b39e89cd2342593`.

The TT/0 °C 200 ps clock-slew rising-data endpoint also passes: Q0/Q1 minima
are 1.79954/1.79937 V instead of the preceding 1.43671/1.43155 V. Waveform:
`6c045bcf6310bccb204d57013219aee5605ebb85b0eaab84a84484a851990b4d`.
Results are under `rx_aperture/7636dbd7a4c55979`. These three endpoints
establish improvement in matched loaded native fixtures, not complete RX timing
qualification. All remaining endpoint and 480-condition gates are unchanged.

`probe_rx_limiting.py` separately queues both-polarity +800 ps setup diagnostics
at SS/0 °C, SS/40 °C and SF/40 °C, all with 200 ps clock slew, 20 ps data slew
and original 20 fF loads. This uses the same audited parent network, captured
original fixture/measurement code and shared real slot leases. Its artifact and
pass flags are explicitly diagnostic. These early limiting cases do not replace
any condition in the complete aperture table or relax its requirements.


The limiting `buf_4` diagnostics expose insufficient margin outside the initial
seed set. At SS/0 °C with 200 ps clock slew, the rising-data +800 ps endpoint
has Q0/Q1 minima 1.40981/1.29742 V. The falling-data endpoint has maxima
1.27975/1.36301 V. SS/40 °C also fails: rising minima 1.40837/1.30168 V,
falling maxima 1.29609/1.38573 V. The original 1.44/0.36 V criteria and
0.80–1.05 ns publication window remain unchanged. Completed diagnostic records
are under `rx_limiting/c004ea34d7420fa7`; these failures prevent selecting the
candidate despite its passing faster-clock-slew SS seeds and TT seeds.

The stronger proposed path uses retained `dfrtp_4` data-publication flops and
retained `buf_8` public data drivers. Sampler polarity/edge, run/reset behavior,
pair ordering, pipeline latency and unit-strength VALID drive are preserved.
Stronger publication flops account for the larger buffer input load; actual
native timing must establish the result. The independent generic/native RX
functional regression passes all 54 cases with 1,186,794 bits per mode under
`rx_buffered_rtl/0adf6d1bf20dab6c`. No physical/electrical pass is claimed for
this new source. Its hardening, extraction/audit and loaded limiting tests are
next, after active users of shared RX flow helpers finish. A watcher requests
retirement of the failed candidate coordinator only when it owns no SPICE lease
and has no SPICE descendants; all current native traces are preserved.
