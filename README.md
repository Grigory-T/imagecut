# Imagecut

Small dependency-free Python module for choosing integer before-pixel vertical
cut positions while avoiding forbidden before-pixel coordinates.

The optimizer is a fast heuristic, not an exact global optimizer. It starts from
equal-width cuts, snaps them to allowed before-pixel coordinates, improves one
cut at a time, and tries several nearby part counts.

## Function

```python
from vertical_cuts import IntegerCutResult, find_good_integer_vertical_cuts

result: IntegerCutResult = find_good_integer_vertical_cuts(
    width=300.0,
    height=100.0,
    forbidden_zones=[(95, 105), (198, 202)],
    target_ratio=1.0,
    max_log_error_weight=1.0,
)

print(result["cuts"])
```

Main output:

```python
result["cuts"]  # list[int], before-pixel cut coordinates
```

## Pixel/Cut Convention

This is the core convention used everywhere in the repo:

- All pixel numbering is zero-based.
- Pixels are indexed `0, 1, ..., width - 1`.
- A returned cut value `x` means: insert the vertical cut **before pixel `x`**.
- Therefore `x=55` means the cut is between pixel `54` and pixel `55`.
- Valid internal cuts are `1, 2, ..., normalized_width - 1`.
- `x=0` would mean "cut before pixel `0`"; this is the left image boundary,
  so it is not a valid internal cut and is never returned.
- `x=normalized_width - 1` means "cut before the last pixel"; this is a valid
  internal cut.
- `x=normalized_width` is the right image boundary, not an internal cut.
- If the previous cut is `previous_cut`, then a cut before pixel `x` creates a
  part width of `x - previous_cut`.
- Example: cuts `[106, 203]` on width `300` create part widths
  `[106, 97, 97]`: pixels `0..105`, `106..202`, and `203..299`.

## Required Inputs

- `width: int | float`
  Full image width in pixels. Must be finite and positive. It is rounded to the
  nearest integer pixel before optimization. Valid internal cut coordinates are
  before-pixel values `1, 2, ..., normalized_width - 1`.
- `height: int | float`
  Full image height in pixels. Must be finite and positive. It is rounded to the
  nearest integer pixel before optimization.
- `forbidden_zones`
  Horizontal ranges of pixels before which cuts are not allowed. Several common
  input shapes are accepted; all are normalized to integer inclusive
  before-pixel intervals.
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

`forbidden_zones` is the important input boundary. A forbidden zone contains the
pixel indices **before which** a cut cannot be inserted.

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
- Coordinates use the image pixel x-axis: pixels are `0..normalized_width-1`.
- A coordinate `x` means the candidate cut before pixel `x`, not a cut through
  pixel `x`.
- Valid cut positions are only internal before-pixel coordinates:
  `1..normalized_width-1`.
- Forbidden zones are inclusive for integer before-pixel cut coordinates.
- Example: `(5, 8)` forbids cuts before pixels `5, 6, 7, 8`.
- In boundary terms, `(5, 8)` forbids cuts between `4|5`, `5|6`, `6|7`, and
  `7|8`.
- Float endpoints are allowed. Integer cut before pixel `x` is forbidden when
  `min(x1, x2) <= x <= max(x1, x2)`.
- Internally this means `lo = ceil(min_endpoint - clearance)` and
  `hi = floor(max_endpoint + clearance)`.
- Zones outside the image are clipped to internal before-pixel cut coordinates.
- Zones that do not contain any valid internal before-pixel cut are ignored.
- Overlapping, touching, or duplicate zones are accepted and merged internally.
- Clean non-overlapping input is still preferred because it is easier to review.
- Unrecognized zone objects fail fast with `TypeError`.

## Optional Inputs

- `center_weight: float = 1e-4`
  Secondary weight for preferring the middle of the allowed interval containing
  a cut. Use `0.0` to disable this preference.
- `mean_log_square_weight: float = 1.0`
  Weight for the average squared multiplicative width error:
  `mean(log(part_width / target_width)^2)`.
- `max_log_error_weight: float = 1.0`
  Weight for the worst part error:
  `max(abs(log(part_width / target_width)))`. Increase this when the main goal
  is to avoid any very bad part.
- `part_count_radius: int | float = 3`
  Number of nearby part counts to try around the ideal count. Rounded to an
  integer.
- `max_passes: int | float = 12`
  Local improvement passes for each candidate solution. Rounded to an integer.
- `local_radius: int | float = 64`
  Search radius around useful anchor positions when an interval is large.
  Rounded to an integer.
- `exhaustive_scan_limit: int | float = 3000`
  If a local search has at most this many allowed before-pixel coordinates,
  check all of them. Rounded to an integer and must be at least `1`.
- `clearance: int | float = 0`
  Extra safety margin around every forbidden zone. Rounded upward to an integer
  so fractional clearance is conservative.

## Loss Function

The width-quality part of the objective is:

```text
width_loss =
    mean_log_square_weight
    * mean(log(part_width_i / target_width)^2)
    +
    max_log_error_weight
    * max(abs(log(part_width_i / target_width)))
```

The full objective is:

```text
objective =
    width_loss
    +
    center_weight * mean(center_penalty(cut_i))
```

The mean squared log term keeps parts good on average. The max absolute log term
protects the worst part, so one very bad segment is penalized even if the
average is acceptable. The log ratio makes `50` vs target `100` and `200` vs
target `100` symmetric multiplicative errors.

The center term is also averaged, not summed, so it stays comparable across
solutions with different numbers of cuts. With no cuts, the center term is `0`.

## Output Structure

The function returns a dictionary with these keys:

- `cuts: list[int]`
  Sorted before-pixel x coordinates for vertical cuts. A value `x` means the cut
  is inserted before pixel `x`, between pixels `x - 1` and `x`.
- `part_widths: list[int]`
  Width of every resulting image part under the before-pixel convention.
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
  Combined loss value. Lower is better; useful only for comparing candidate
  results from this function with the same loss parameters.
- `allowed_intervals: list[tuple[int, int]]`
  Inclusive before-pixel intervals where cuts are allowed.
- `forbidden_zones_used: list[tuple[int, int]]`
  Normalized, clipped, merged forbidden before-pixel intervals.
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
before pixels `[100, 200]`, but those before-pixel coordinates are forbidden, so
the algorithm moves them to nearby allowed before-pixel coordinates.

For the example above:

- `106` means cut before pixel `106`, between pixels `105` and `106`.
- `203` means cut before pixel `203`, between pixels `202` and `203`.
