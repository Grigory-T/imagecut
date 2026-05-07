# Imagecut

Small dependency-free Python module for choosing integer-pixel vertical cut
positions while avoiding forbidden x-coordinate zones.

The optimizer is a fast heuristic, not an exact global optimizer. It starts from
equal-width cuts, snaps them to allowed pixels, improves one cut at a time, and
tries several nearby part counts.

## Function

```python
from vertical_cuts import IntegerCutResult, find_good_integer_vertical_cuts

result: IntegerCutResult = find_good_integer_vertical_cuts(
    width=300.0,
    height=100.0,
    forbidden_zones=[(95, 105), (198, 202)],
    target_ratio=1.0,
)

print(result["cuts"])
```

Main output:

```python
result["cuts"]  # list[int]
```

## Required Inputs

- `width: int | float`
  Full image width in pixels. Must be finite and positive. It is rounded to the
  nearest integer pixel before optimization. Valid internal cut coordinates are
  `1, 2, ..., normalized_width - 1`.
- `height: int | float`
  Full image height in pixels. Must be finite and positive. It is rounded to the
  nearest integer pixel before optimization.
- `forbidden_zones`
  Horizontal x-coordinate ranges where cuts are not allowed. Several common
  input shapes are accepted; all are normalized to integer inclusive intervals.
- `target_ratio: float`
  Desired aspect ratio for every part, defined as `height / part_width`. Must be
  finite and positive. For example, normalized `height=100` and
  `target_ratio=1.0` gives target part width `100`.

Dimension conversion:

- `width` and `height` may be int or float-like values.
- They are rounded to the nearest integer pixel using half-up rounding:
  `300.2 -> 300`, `300.5 -> 301`.
- Values must still produce a positive integer after rounding.
- The core algorithm remains integer-based after this normalization step.

## Forbidden Zone Contract

`forbidden_zones` is the important input boundary.

Accepted zone input forms:

- Iterable of numeric pairs:
  `[(95, 105), (198, 202)]`
- One numeric pair:
  `(95, 105)`
- Mapping for one zone:
  `{"start": 95, "end": 105}`
- Object with equivalent attributes:
  `obj.start`, `obj.end`
- Mapping that contains zones under one of these keys:
  `"zones"`, `"forbidden_zones"`, `"ranges"`, `"intervals"`
- Mapping of names to zones:
  `{"title": (95, 105), "label": {"x1": 198, "x2": 202}}`

Recognized pair names for mappings or object attributes:

- `start` / `end`
- `left` / `right`
- `lo` / `hi`
- `low` / `high`
- `min` / `max`
- `x1` / `x2`
- `from` / `to` for mappings
- `a` / `b`

Normalization rules:

- Sorting is not required. The function sorts zones internally.
- Pair order is not important. `(105, 95)` is accepted and normalized.
- Coordinates must be finite numeric values; `NaN` and infinite values are
  rejected.
- Coordinates use the same x-axis as the image: left edge `0`, right edge
  `width`.
- Valid cut positions are only internal integer pixels:
  `1..normalized_width-1`.
- Forbidden zones are inclusive for integer cut coordinates.
- Example: `(5, 8)` forbids cuts at `5, 6, 7, 8`.
- Float endpoints are allowed. Integer cut `x` is forbidden when
  `min(x1, x2) <= x <= max(x1, x2)`.
- Internally this means `lo = ceil(min_endpoint - clearance)` and
  `hi = floor(max_endpoint + clearance)`.
- Zones outside the image are clipped to internal cut coordinates.
- Zones that do not contain any valid internal integer cut are ignored.
- Overlapping, touching, or duplicate zones are accepted and merged internally.
- Clean non-overlapping input is still preferred because it is easier to review.
- Unrecognized zone objects fail fast with `TypeError`.

## Optional Inputs

- `center_weight: float = 1e-4`
  Secondary weight for preferring the middle of the allowed interval containing
  a cut. Use `0.0` to disable this preference.
- `part_count_radius: int | float = 3`
  Number of nearby part counts to try around the ideal count. Rounded to an
  integer.
- `max_passes: int | float = 12`
  Local improvement passes for each candidate solution. Rounded to an integer.
- `local_radius: int | float = 64`
  Search radius around useful anchor positions when an interval is large.
  Rounded to an integer.
- `exhaustive_scan_limit: int | float = 3000`
  If a local search has at most this many allowed pixels, check all of them.
  Rounded to an integer and must be at least `1`.
- `clearance: int | float = 0`
  Extra safety margin around every forbidden zone. Rounded upward to an integer
  so fractional clearance is conservative.

## Output Structure

The function returns a dictionary with these keys:

- `cuts: list[int]`
  Sorted integer x coordinates for vertical cuts.
- `part_widths: list[int]`
  Width of every resulting image part.
- `part_aspect_ratios_H_over_W: list[float]`
  Aspect ratio of every part, using `height / part_width`.
- `n_parts: int`
  Number of resulting parts.
- `n_cuts: int`
  Number of cuts.
- `target_width: float`
  Ideal part width calculated as `normalized_height / target_ratio`.
- `target_ratio_H_over_W: float`
  Echo of the requested target ratio.
- `objective: float`
  Lower is better; useful only for comparing candidate results from this
  function.
- `allowed_intervals: list[tuple[int, int]]`
  Inclusive integer intervals where cuts are allowed.
- `forbidden_zones_used: list[tuple[int, int]]`
  Normalized, clipped, merged forbidden integer intervals.
- `parameters: dict`
  Echo of tuning parameters used for the run.

## Example/Test

```bash
python3 example_test.py
```

Expected core result for the included example:

```python
cuts: [106, 203]
part_widths: [106, 97, 97]
```

The natural cuts for `width=300`, `height=100`, `target_ratio=1.0` would be
near `[100, 200]`, but those coordinates are forbidden, so the algorithm moves
them to nearby allowed integer pixels.
