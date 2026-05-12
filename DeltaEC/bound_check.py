"""
bound_check.py
--------------
Boundary checking helpers for DeltaEC segment properties.

Designed to work alongside deltaec_parser.DeltaECFile.

Functions
---------
bound_check(value, lower, upper)
    Core numeric check — works on any float.

check(dec, seg_num, letter, lower, upper)
    Extract a property from a parsed DeltaEC file and check its bounds.
    Returns a CheckResult namedtuple with .ok, .value, .lower, .upper,
    .label, .units so callers can report results without re-querying.

check_many(dec, specs)
    Run multiple checks at once from a list of spec dicts.
    Returns a list of CheckResult objects.

Bound conventions
-----------------
Pass None for a one-sided bound:
    check(dec, 14, 'H', 300, None)   # only a lower bound
    check(dec, 14, 'H', None, 320)   # only an upper bound
    check(dec, 14, 'H', 300, 320)    # both bounds (inclusive)
"""

from collections import namedtuple
from typing import Optional

# Import the parser — adjust the import if you keep them in separate files.
from deltaec_parser import DeltaECFile


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

CheckResult = namedtuple(
    'CheckResult',
    ['ok', 'seg_num', 'letter', 'value', 'lower', 'upper', 'label', 'units']
)


def _fmt_result(r: CheckResult) -> str:
    """Human-readable summary of a CheckResult."""
    status = 'PASS' if r.ok else 'FAIL'
    lo = f"{r.lower}" if r.lower is not None else '-inf'
    hi = f"{r.upper}" if r.upper is not None else '+inf'
    return (
        f"[{status}] Seg {r.seg_num}{r.letter}  {r.label}  "
        f"{r.value:g} {r.units}  "
        f"(bounds: [{lo}, {hi}])"
    )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def bound_check(
    value: float,
    lower: Optional[float],
    upper: Optional[float],
) -> bool:
    """
    Return True if *value* falls within [lower, upper] (inclusive).

    Pass ``None`` for a one-sided or unbounded check:
        bound_check(42.0, 40.0, None)   # True  (>= 40, no upper limit)
        bound_check(42.0, None, 40.0)   # False (no lower, but > 40)

    Parameters
    ----------
    value : float
    lower : float | None   Lower bound (inclusive). None = no lower limit.
    upper : float | None   Upper bound (inclusive). None = no upper limit.

    Returns
    -------
    bool
    """
    if lower is not None and value < lower:
        return False
    if upper is not None and value > upper:
        return False
    return True


def check(
    dec: DeltaECFile,
    seg_num: int,
    letter: str,
    lower: Optional[float],
    upper: Optional[float],
) -> CheckResult:
    """
    Extract a property from *dec* and check it against [lower, upper].

    Parameters
    ----------
    dec     : DeltaECFile   Parsed DeltaEC file.
    seg_num : int           Segment number.
    letter  : str           Property letter ('a'–'z' input, 'A'–'Z' output).
    lower   : float | None  Lower bound (inclusive). None = unbounded.
    upper   : float | None  Upper bound (inclusive). None = unbounded.

    Returns
    -------
    CheckResult(ok, seg_num, letter, value, lower, upper, label, units)

    Raises
    ------
    KeyError  if segment or letter not found (propagated from DeltaECFile).
    """
    value, label, units = dec.get_full(seg_num, letter)
    ok = bound_check(value, lower, upper)
    return CheckResult(ok, seg_num, letter, value, lower, upper, label, units)


def check_many(dec: DeltaECFile, specs: list) -> list:
    """
    Run multiple bound checks in one call.

    Parameters
    ----------
    dec   : DeltaECFile
    specs : list of dicts, each with keys:
                seg_num : int
                letter  : str
                lower   : float | None
                upper   : float | None
            Example::

                specs = [
                    {'seg_num': 0,  'letter': 'b', 'lower': 40,  'upper': 50},
                    {'seg_num': 14, 'letter': 'H', 'lower': 300, 'upper': 320},
                    {'seg_num': 15, 'letter': 'e', 'lower': 35,  'upper': None},
                ]

    Returns
    -------
    list[CheckResult]
    """
    results = []
    for s in specs:
        results.append(check(dec, s['seg_num'], s['letter'],
                             s.get('lower'), s.get('upper')))
    return results


def print_results(results, show_passing: bool = True):
    """Print a table of CheckResult objects."""
    for r in results:
        if show_passing or not r.ok:
            print(_fmt_result(r))
    failures = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failures)}/{len(results)} checks passed.")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    dec = DeltaECFile('jg_00.out')

    # --- Single check ---
    result = check(dec, 27, 'H', 300, 320)
    print(_fmt_result(result))

    # --- One-sided checks ---
    print(_fmt_result(check(dec, 33, 'e', 35, None)))   # HHX heat >= 35 W
    print(_fmt_result(check(dec, 0,  'b', None, 50)))   # freq <= 50 Hz

    # --- Batch checks ---
    print("\n--- Batch checks ---")
    specs = [
        {'seg_num': 0,  'letter': 'b', 'lower': 40,   'upper': 50},    # Freq
        {'seg_num': 0,  'letter': 'c', 'lower': 300,  'upper': 320},   # TBeg
        {'seg_num': 27, 'letter': 'G', 'lower': 305,  'upper': 315},   # Regen TBeg
        {'seg_num': 27, 'letter': 'H', 'lower': 300,  'upper': 320},   # Regen TEnd
        {'seg_num': 27, 'letter': 'F', 'lower': 0,    'upper': None},  # Regen Edot >= 0
        {'seg_num': 33, 'letter': 'e', 'lower': 35,   'upper': 45},    # HHX heat in
        {'seg_num': 33, 'letter': 'H', 'lower': 650,  'upper': 750},   # HHX solid T
        {'seg_num': 17, 'letter': 'I', 'lower': 305,  'upper': 315},   # SOFTEND T  (expect FAIL)
    ]
    results = check_many(dec, specs)
    print_results(results)
