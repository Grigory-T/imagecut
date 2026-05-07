from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
from math import ceil, floor, isfinite, log
from operator import index
from typing import Any, Iterable, Literal, Optional, TypedDict


Preference = Literal["nearest", "left", "right"]
Direction = Literal["ltr", "rtl"]


class CutParameters(TypedDict):
    center_weight: float
    part_count_radius: int
    max_passes: int
    local_radius: int
    exhaustive_scan_limit: int
    clearance: int


class IntegerCutResult(TypedDict):
    cuts: list[int]
    part_widths: list[int]
    part_aspect_ratios_H_over_W: list[float]
    n_parts: int
    n_cuts: int
    target_width: float
    target_ratio_H_over_W: float
    objective: float
    allowed_intervals: list[tuple[int, int]]
    forbidden_zones_used: list[tuple[int, int]]
    parameters: CutParameters


def find_good_integer_vertical_cuts(
    *,
    width: int,
    height: int,
    forbidden_zones: Iterable[tuple[float, float]],
    target_ratio: float,
    center_weight: float = 1e-4,
    part_count_radius: int = 3,
    max_passes: int = 12,
    local_radius: int = 64,
    exhaustive_scan_limit: int = 3000,
    clearance: int = 0,
) -> IntegerCutResult:
    """
    Fast heuristic integer-pixel solution for vertical image cuts.

    Coordinate convention:
        Valid internal cuts are integer x coordinates 1, 2, ..., width - 1.
        A cut at x creates a part width of x - previous_cut.

    Forbidden zones:
        Zones are inclusive for integer cut coordinates. Sorting is not
        required. Pair order is not important. For example, (8, 5) is
        normalized to (5, 8), forbidding x = 5, 6, 7, 8.

    Optimization target:
        target_ratio = height / part_width
        target_width = height / target_ratio

    This is a fast multi-start local search, not an exact global optimizer.
    """

    W = _as_int("width", width)
    H = _as_int("height", height)
    part_count_radius = _as_int("part_count_radius", part_count_radius)
    max_passes = _as_int("max_passes", max_passes)
    local_radius = _as_int("local_radius", local_radius)
    exhaustive_scan_limit = _as_int(
        "exhaustive_scan_limit",
        exhaustive_scan_limit,
    )
    clearance = _as_int("clearance", clearance)
    target_ratio = _as_finite_float("target_ratio", target_ratio)
    center_weight = _as_finite_float("center_weight", center_weight)

    if W <= 0:
        raise ValueError("width must be positive")
    if H <= 0:
        raise ValueError("height must be positive")
    if target_ratio <= 0:
        raise ValueError("target_ratio must be positive")
    if center_weight < 0:
        raise ValueError("center_weight must be non-negative")
    if part_count_radius < 0:
        raise ValueError("part_count_radius must be non-negative")
    if max_passes < 0:
        raise ValueError("max_passes must be non-negative")
    if local_radius < 0:
        raise ValueError("local_radius must be non-negative")
    if exhaustive_scan_limit < 1:
        raise ValueError("exhaustive_scan_limit must be >= 1")
    if clearance < 0:
        raise ValueError("clearance must be non-negative")

    target_width = H / float(target_ratio)

    forbidden_intervals = _normalize_forbidden_zones(
        width=W,
        forbidden_zones=forbidden_zones,
        clearance=clearance,
    )
    allowed = _build_allowed_intervals(W, forbidden_intervals)
    allowed_starts = [lo for lo, _ in allowed]
    allowed_ends = [hi for _, hi in allowed]

    @lru_cache(maxsize=None)
    def interval_for_x(x: int) -> Optional[tuple[int, int]]:
        idx = bisect_right(allowed_starts, x) - 1

        if idx >= 0 and x <= allowed_ends[idx]:
            return allowed[idx]

        return None

    @lru_cache(maxsize=None)
    def allowed_overlaps(low: int, high: int) -> list[tuple[int, int]]:
        if low > high:
            return []

        overlaps: list[tuple[int, int]] = []

        for lo, hi in allowed:
            if hi < low:
                continue
            if lo > high:
                break

            a = max(lo, low)
            b = min(hi, high)

            if a <= b:
                overlaps.append((a, b))

        return overlaps

    def is_allowed(x: int) -> bool:
        return interval_for_x(x) is not None

    def nearest_allowed_in_range(
        target: float,
        low: int,
        high: int,
        preference: Preference,
    ) -> Optional[int]:
        overlaps = allowed_overlaps(low, high)

        if not overlaps:
            return None

        t = int(round(target))

        if preference == "nearest":
            candidates: list[int] = []

            for a, b in overlaps:
                if a <= t <= b:
                    candidates.append(t)
                elif t < a:
                    candidates.append(a)
                else:
                    candidates.append(b)

            return min(candidates, key=lambda x: (abs(x - t), x))

        if preference == "left":
            left_candidates: list[int] = []
            right_candidates: list[int] = []

            for a, b in overlaps:
                if a <= t:
                    left_candidates.append(min(t, b))
                if b >= t:
                    right_candidates.append(max(t, a))

            if left_candidates:
                return max(left_candidates)

            return min(right_candidates, key=lambda x: abs(x - t))

        if preference == "right":
            left_candidates = []
            right_candidates = []

            for a, b in overlaps:
                if a <= t:
                    left_candidates.append(min(t, b))
                if b >= t:
                    right_candidates.append(max(t, a))

            if right_candidates:
                return min(right_candidates)

            return min(left_candidates, key=lambda x: abs(x - t))

        raise ValueError("preference must be 'nearest', 'left', or 'right'")

    @lru_cache(maxsize=None)
    def part_loss(part_width: int) -> float:
        if part_width <= 0:
            return 1e100

        return log(part_width / target_width) ** 2

    @lru_cache(maxsize=None)
    def center_penalty(x: int) -> float:
        interval = interval_for_x(x)

        if interval is None:
            return 1e100

        lo, hi = interval

        if lo == hi:
            return 0.0

        midpoint = (lo + hi) / 2.0
        half_width = (hi - lo) / 2.0

        return ((x - midpoint) / half_width) ** 2

    def objective(cuts: list[int]) -> tuple[float, list[int], list[float]]:
        points = [0, *cuts, W]
        part_widths = [
            points[i + 1] - points[i]
            for i in range(len(points) - 1)
        ]

        value = sum(part_loss(w) for w in part_widths)
        value += center_weight * sum(center_penalty(x) for x in cuts)

        ratios = [H / w for w in part_widths]

        return value, part_widths, ratios

    def make_initial_cuts(
        n_parts: int,
        *,
        direction: Direction,
        preference: Preference,
    ) -> Optional[list[int]]:
        n_cuts = n_parts - 1

        if n_cuts == 0:
            return []

        if not allowed:
            return None

        ideal_cuts = [
            j * W / n_parts
            for j in range(1, n_parts)
        ]

        if direction == "ltr":
            cuts: list[int] = []
            previous = 0

            for i, ideal_x in enumerate(ideal_cuts):
                remaining_after = n_cuts - i - 1
                low = previous + 1
                high = W - remaining_after - 1

                x = nearest_allowed_in_range(
                    ideal_x,
                    low,
                    high,
                    preference,
                )

                if x is None:
                    return None

                cuts.append(x)
                previous = x

            return cuts

        if direction == "rtl":
            cuts_optional: list[Optional[int]] = [None] * n_cuts
            next_cut = W

            for i in range(n_cuts - 1, -1, -1):
                ideal_x = ideal_cuts[i]
                remaining_before = i
                low = remaining_before + 1
                high = next_cut - 1

                x = nearest_allowed_in_range(
                    ideal_x,
                    low,
                    high,
                    preference,
                )

                if x is None:
                    return None

                cuts_optional[i] = x
                next_cut = x

            cuts = [
                int(x)
                for x in cuts_optional
                if x is not None
            ]

            if len(cuts) != n_cuts:
                return None

            return cuts

        raise ValueError("direction must be 'ltr' or 'rtl'")

    def candidate_positions_for_cut(
        *,
        left: int,
        right: int,
        current: int,
    ) -> list[int]:
        low = left + 1
        high = right - 1

        if low > high:
            return []

        overlaps = allowed_overlaps(low, high)

        if not overlaps:
            return []

        total_allowed_count = sum(b - a + 1 for a, b in overlaps)
        candidates: set[int] = set()
        anchors = [
            current,
            round((left + right) / 2),
            round(left + target_width),
            round(right - target_width),
        ]

        if total_allowed_count <= exhaustive_scan_limit:
            for a, b in overlaps:
                candidates.update(range(a, b + 1))
        else:
            for a, b in overlaps:
                interval_mid = round((a + b) / 2)
                interval_anchors = [*anchors, a, b, interval_mid]

                for anchor in interval_anchors:
                    x = min(max(int(anchor), a), b)
                    candidates.add(x)

                    lo = max(a, x - local_radius)
                    hi = min(b, x + local_radius)
                    candidates.update(range(lo, hi + 1))

        return sorted(
            x for x in candidates
            if low <= x <= high and is_allowed(x)
        )

    def improve(cuts: list[int]) -> list[int]:
        cuts = sorted(cuts)

        for _ in range(max_passes):
            changed = False
            orders = [
                range(len(cuts)),
                range(len(cuts) - 1, -1, -1),
            ]

            for order in orders:
                for i in order:
                    left = 0 if i == 0 else cuts[i - 1]
                    right = W if i == len(cuts) - 1 else cuts[i + 1]
                    current = cuts[i]

                    candidates = candidate_positions_for_cut(
                        left=left,
                        right=right,
                        current=current,
                    )

                    if not candidates:
                        continue

                    def local_cost(x: int) -> float:
                        return (
                            part_loss(x - left)
                            + part_loss(right - x)
                            + center_weight * center_penalty(x)
                        )

                    best_x = current
                    best_cost = local_cost(current)

                    for x in candidates:
                        cost = local_cost(x)

                        if cost + 1e-15 < best_cost:
                            best_cost = cost
                            best_x = x

                    if best_x != current:
                        cuts[i] = best_x
                        changed = True

            if not changed:
                break

        return cuts

    ideal_parts = W / target_width
    center_part_count = max(1, int(round(ideal_parts)))
    min_parts = max(1, center_part_count - part_count_radius)
    max_parts = max(1, center_part_count + part_count_radius)
    candidate_part_counts = sorted({
        1,
        *range(min_parts, max_parts + 1),
    })
    starts: list[tuple[Direction, Preference]] = [
        ("ltr", "nearest"),
        ("ltr", "left"),
        ("ltr", "right"),
        ("rtl", "nearest"),
        ("rtl", "left"),
        ("rtl", "right"),
    ]

    best_result: Optional[IntegerCutResult] = None
    seen_starts: set[tuple[int, ...]] = set()

    for n_parts in candidate_part_counts:
        if n_parts == 1:
            initial_solutions = [[]]
        else:
            initial_solutions = []

            for direction, preference in starts:
                init = make_initial_cuts(
                    n_parts,
                    direction=direction,
                    preference=preference,
                )

                if init is not None:
                    initial_solutions.append(init)

        for init in initial_solutions:
            key = tuple(init)

            if key in seen_starts:
                continue

            seen_starts.add(key)

            cuts = improve(init)
            score, part_widths, ratios = objective(cuts)

            result: IntegerCutResult = {
                "cuts": cuts,
                "part_widths": part_widths,
                "part_aspect_ratios_H_over_W": ratios,
                "n_parts": len(part_widths),
                "n_cuts": len(cuts),
                "target_width": target_width,
                "target_ratio_H_over_W": target_ratio,
                "objective": score,
                "allowed_intervals": allowed,
                "forbidden_zones_used": forbidden_intervals,
                "parameters": {
                    "center_weight": center_weight,
                    "part_count_radius": part_count_radius,
                    "max_passes": max_passes,
                    "local_radius": local_radius,
                    "exhaustive_scan_limit": exhaustive_scan_limit,
                    "clearance": clearance,
                },
            }

            if best_result is None or score < best_result["objective"]:
                best_result = result

    if best_result is None:
        raise RuntimeError("No feasible solution found.")

    return best_result


def _as_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an int, not bool")

    try:
        return index(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be an int") from exc


def _as_finite_float(name: str, value: Any) -> float:
    value = float(value)

    if not isfinite(value):
        raise ValueError(f"{name} must be finite")

    return value


def _normalize_forbidden_zones(
    *,
    width: int,
    forbidden_zones: Iterable[tuple[float, float]],
    clearance: int,
) -> list[tuple[int, int]]:
    forbidden: list[tuple[int, int]] = []

    for a, b in forbidden_zones:
        a_float = _as_finite_float("forbidden zone coordinate", a)
        b_float = _as_finite_float("forbidden zone coordinate", b)
        lo_raw = min(a_float, b_float) - clearance
        hi_raw = max(a_float, b_float) + clearance

        # Integer x is forbidden when lo_raw <= x <= hi_raw.
        lo = max(1, ceil(lo_raw))
        hi = min(width - 1, floor(hi_raw))

        if lo <= hi:
            forbidden.append((lo, hi))

    forbidden.sort()

    merged: list[list[int]] = []

    for lo, hi in forbidden:
        if not merged or lo > merged[-1][1] + 1:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)

    return [(lo, hi) for lo, hi in merged]


def _build_allowed_intervals(
    width: int,
    forbidden_intervals: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    allowed: list[tuple[int, int]] = []
    cursor = 1

    for lo, hi in forbidden_intervals:
        if cursor <= lo - 1:
            allowed.append((cursor, lo - 1))

        cursor = hi + 1

    if cursor <= width - 1:
        allowed.append((cursor, width - 1))

    return allowed
