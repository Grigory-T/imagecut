from __future__ import annotations

from time import perf_counter
from types import SimpleNamespace

from vertical_cuts import find_good_integer_vertical_cuts


def main() -> None:
    width = 300
    height = 100
    target_ratio = 1.0
    forbidden_zones = [
        (95, 105),
        (198, 202),
    ]

    started = perf_counter()
    result = find_good_integer_vertical_cuts(
        width=width,
        height=height,
        forbidden_zones=forbidden_zones,
        target_ratio=target_ratio,
        center_weight=1e-4,
    )
    elapsed_ms = (perf_counter() - started) * 1000.0

    print(f"elapsed_ms: {elapsed_ms:.3f}")
    print(f"target_width: {result['target_width']:.6f}")
    print(f"n_parts: {result['n_parts']}")
    print("cuts:", result["cuts"])
    print("part_widths:", result["part_widths"])
    print(
        "part_aspect_ratios_H_over_W:",
        [round(x, 6) for x in result["part_aspect_ratios_H_over_W"]],
    )
    print(f"objective: {result['objective']:.9f}")

    assert result["n_parts"] == 3
    assert result["cuts"] == [106, 203]
    assert result["part_widths"] == [106, 97, 97]
    assert all(isinstance(cut, int) for cut in result["cuts"])
    assert all(1 <= cut <= width - 1 for cut in result["cuts"])
    assert result["cuts"] == sorted(result["cuts"])

    for cut in result["cuts"]:
        assert not any(lo <= cut <= hi for lo, hi in forbidden_zones)

    normalized_result = find_good_integer_vertical_cuts(
        width=width,
        height=height,
        forbidden_zones=[
            (202, 198),
            (105, 95),
        ],
        target_ratio=target_ratio,
        center_weight=1e-4,
    )
    assert normalized_result["cuts"] == result["cuts"]

    flexible_input_result = find_good_integer_vertical_cuts(
        width=300.2,
        height=100.1,
        forbidden_zones={
            "zones": [
                {"start": 95.0, "end": 105.0},
                SimpleNamespace(x1=202.0, x2=198.0),
            ],
        },
        target_ratio=target_ratio,
        center_weight=1e-4,
    )
    assert flexible_input_result["cuts"] == result["cuts"]
    assert flexible_input_result["forbidden_zones_used"] == [
        (95, 105),
        (198, 202),
    ]

    max_ratio_error = max(
        abs(ratio - target_ratio)
        for ratio in result["part_aspect_ratios_H_over_W"]
    )
    assert max_ratio_error < 0.06
    assert elapsed_ms < 50.0

    stress_start = perf_counter()
    stress_result = find_good_integer_vertical_cuts(
        width=5000,
        height=250,
        forbidden_zones=[(x, x + 8) for x in range(180, 4900, 120)],
        target_ratio=1.0,
        center_weight=1e-4,
    )
    stress_ms = (perf_counter() - stress_start) * 1000.0
    stress_max_width_error = max(
        abs(w - stress_result["target_width"])
        for w in stress_result["part_widths"]
    )

    print(f"stress_elapsed_ms: {stress_ms:.3f}")
    print(f"stress_n_parts: {stress_result['n_parts']}")
    print(f"stress_max_width_error: {stress_max_width_error:.6f}")

    assert stress_result["n_parts"] == 20
    assert stress_max_width_error <= 1.0
    assert stress_ms < 250.0


if __name__ == "__main__":
    main()
