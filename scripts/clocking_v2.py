# SPDX-License-Identifier: GPL-3.0-only
"""Executable clocking/training contract; no invented SKY130 delay constants.

Tables supplied to these algorithms must come from separately admitted native
characterization. Unit-test tables exercise algorithms only, never PHY evidence.
"""
from dataclasses import dataclass
import math

MARKER = 0xffff0000
END_MARKER = 0x0000ffff


def bits(value, width):
    return tuple((value >> i) & 1 for i in reversed(range(width)))


def training_frame():
    state = 0x7f; stream = list(bits(MARKER, 32))
    for _ in range(224):
        stream.append((state >> 6) & 1)
        state = ((state << 1) & 0x7f) | (((state >> 6) ^ (state >> 5)) & 1)
    return tuple(stream)


def marker_positions(stream, marker=MARKER):
    stream = tuple(stream); target = bits(marker, 32)
    if len(stream) < 32:
        raise ValueError('Need at least 32 bits')
    extended = stream + stream[:31]
    return [i for i in range(len(stream)) if extended[i:i+32] == target]


def align_training(stream, minimum_frames=4):
    """Find all frame rotations, requiring complete exact matching frames.

    Serial ordering is chronological. Pair consumers must try both pair phases;
    an arbitrary reset alignment cannot be assumed from the DDR valid signal.
    """
    frame = training_frame(); stream = tuple(stream)
    if minimum_frames < 4:
        raise ValueError('Four complete frames required')
    size = 256 * minimum_frames
    return [i for i in range(min(256, len(stream))) if len(stream) - i >= size
            and stream[i:i+size] == frame * minimum_frames]


@dataclass(frozen=True)
class Delay:
    code: int
    lo_ps: float
    hi_ps: float

    def __post_init__(self):
        if (type(self.code) is not int or self.code < 0 or not math.isfinite(self.lo_ps)
                or not math.isfinite(self.hi_ps) or self.lo_ps < 0 or self.hi_ps < self.lo_ps):
            raise ValueError('Invalid conservative delay interval')


def common_legal_codes(corners, maximum_gap_ps=20):
    """Admit a supplied common ordering; do not reorder codes per corner.

    Every interval is disjoint and increasing at each PVT. The maximum possible
    increment, not just nominal means, must meet the legal-gap limit.
    """
    if not corners or maximum_gap_ps <= 0:
        raise ValueError('Missing characterization')
    reference = next(iter(corners.values()))
    codes = [d.code for d in reference]
    if len(codes) < 2 or len(set(codes)) != len(codes):
        raise ValueError('Missing or duplicated delay codes')
    for table in corners.values():
        if [d.code for d in table] != codes:
            raise ValueError('No common legal sequence across PVT')
        for left, right in zip(table, table[1:]):
            if right.lo_ps <= left.hi_ps or right.hi_ps - left.lo_ps > maximum_gap_ps:
                raise ValueError('Nonmonotonic, ambiguous or excessive delay gap')
    return tuple(codes)


def crossing_search(values, target):
    """Coarse first crossing, back off, then fine within the bracket.

    `values` contains the qualified common monotonic legal sequence, not raw
    binary codes. Return the adjacent bounding indices; never wrap a counter.
    """
    if not math.isfinite(target) or not values or any(not math.isfinite(v) for v in values):
        raise ValueError('Invalid delay search')
    if any(a >= b for a, b in zip(values, values[1:])) or not values[0] <= target <= values[-1]:
        raise ValueError('Delay range or monotonicity failure')
    stride = max(1, math.isqrt(len(values)))
    coarse = list(range(0, len(values), stride))
    if coarse[-1] != len(values)-1: coarse.append(len(values)-1)
    for end in coarse:
        if values[end] >= target:
            start = max(0, end-stride)
            for high in range(start, end+1):
                if values[high] >= target:
                    return max(0, high-1), high
    raise AssertionError('Unreachable bounded search')


def balance_sections(tables, period_ps, tolerance_ps=20, confirmations=64):
    """Bounded paper-style fastest-section balancing on measured delay tables.

    Returns only proposed codes. Hardware additionally needs independent tagged
    unwrapped period and 64 detector confirmations before asserting lock.
    """
    if len(tables) != 4 or confirmations < 64 or tolerance_ps <= 0 or period_ps <= 0:
        raise ValueError('Invalid four-section calibration policy')
    for table in tables:
        if not table or any(a >= b for a, b in zip(table, table[1:])):
            raise ValueError('Section characterization is not monotonic')
    indices = [0] * 4
    for _ in range(sum(map(len, tables))):
        delays = [t[i] for t, i in zip(tables, indices)]
        error = sum(delays) - period_ps
        if abs(error) <= tolerance_ps and max(delays)-min(delays) <= 20:
            return dict(indices=indices, total_ps=sum(delays), period_error_ps=error,
                        confirmations_required=confirmations, locked=False)
        if error > tolerance_ps:
            raise ValueError('One-period target skipped; no lock')
        fastest = min(range(4), key=lambda i: (delays[i], i))
        if indices[fastest]+1 == len(tables[fastest]):
            raise ValueError('Fastest section saturated; no lock')
        indices[fastest] += 1
    raise ValueError('Bounded calibration exhausted')


def select_eye(table, passing, minimum_clearance_ps=250):
    """Maximize conservative physical clearance in fully scanned passing runs.

    First and last passing code intervals bound the observed usable window.
    Unmeasured gaps or islands cannot be bridged. No code-index midpoint rule.
    A scan covering a whole clock period plus headroom includes a complete eye;
    an eye clipped at a scan end is deliberately treated conservatively.
    """
    if len(table) != len(passing) or len(table) < 2 or minimum_clearance_ps < 250:
        raise ValueError('Incomplete training scan or weakened policy')
    if any(type(p) is not bool for p in passing):
        raise ValueError('Each code needs an explicit training result')
    common_legal_codes({'scan': table})
    candidates = []; start = 0
    while start < len(table):
        if not passing[start]:
            start += 1; continue
        end = start
        while end+1 < len(table) and passing[end+1]: end += 1
        left, right = table[start].hi_ps, table[end].lo_ps
        for item in table[start:end+1]:
            clearance = min(item.lo_ps-left, right-item.hi_ps)
            if clearance >= minimum_clearance_ps:
                candidates.append((clearance, -item.code, item))
        start = end+1
    if not candidates:
        raise ValueError('No eye with sufficient physical clearance')
    clearance, _, item = max(candidates, key=lambda x: (x[0], x[1]))
    return dict(code=item.code, clearance_ps=clearance, delay_interval_ps=[item.lo_ps, item.hi_ps],
                qualified_phy=False)
