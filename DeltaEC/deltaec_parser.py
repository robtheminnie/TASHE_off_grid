"""
deltaec_parser.py
-----------------
Parse a DeltaEC .out/.sp file into Segment/Property objects.

Usage
-----
    from deltaec_parser import DeltaECFile

    dec = DeltaECFile("detailed_v11.out")

    val = dec.get(14, 'H')                   # -> 304.68  (TEnd K)
    val, label, units = dec.get_full(15, 'e') # -> (40.0, 'HeatIn', 'W')
    prop = dec.get_property(0, 'b')           # Property object

    dec.dump_segment(14)

    for n in dec.segment_numbers():
        seg = dec.segments[n]
        print(n, seg.seg_type, seg.name)
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Property:
    """One input (a–z) or output (A–Z) property of a DeltaEC segment."""
    letter:    str    # 'a'–'z' inputs, 'A'–'Z' outputs
    value:     float
    label:     str    # e.g. 'Area', 'Edot', '|p|'
    units:     str    # e.g. 'm^2', 'W', 'deg'; '' for dimensionless
    flags:     str    # extra tokens on the line: 'G', 'Mstr', '=12H', …
    is_output: bool


@dataclass
class Segment:
    """One DeltaEC segment block (BEGIN, DUCT, HX, STKSCREEN, …)."""
    number:   int
    seg_type: str
    name:     str
    inputs:  dict = field(default_factory=dict)   # lower-letter -> Property
    outputs: dict = field(default_factory=dict)   # upper-letter -> Property

    def get_property(self, letter: str) -> Optional['Property']:
        return self.inputs.get(letter) if letter.islower() else self.outputs.get(letter)


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_NUM = r'[+-]?\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?'

# Left (input) column: value  letter  label  [units]  [flags…]
_RE_INPUT = re.compile(
    r'^\s*(' + _NUM + r')\s+([a-z])\s+(\S+)(?:\s+(\S+))?(.*)?$'
)

# Right (output) column: value  LETTER  label  [units]
# Used with finditer so multiple outputs per line are captured.
_RE_OUTPUT = re.compile(
    r'(' + _NUM + r')\s+([A-Z])\s+(\S+)(?:\s+(\S+))?'
)

# Segment header:  !---- N ----
_RE_SEG_HEADER = re.compile(r'^!-+\s*(\d+)\s*-+')

# Segment type + descriptive name (first non-comment line after header)
_RE_TYPE_LINE = re.compile(r'^([A-Z][A-Z0-9]*)\s*(.*)')

# Lines whose LEFT column we skip entirely (but we still parse their right col)
_RE_LEFT_SKIP = re.compile(
    r'^\s*$'                        # blank
    r'|^!'                          # comment
    r'|^(?:air|helium|argon|nitrogen|ideal|stainless|copper|invar'
    r'|aluminum|brass|nylon|glass|water|oil)\b'   # material / gas type
    r'|^[a-zA-Z]\w*\s*;'          # RPN expression  (e.g.  "1a ;")
    r'|^\s*\d[\d.]*\s*;'          # RPN number      (e.g.  "0.00")
    r'|^0\.00\s*$'                 # bare RPN zero
    r'|^using\b'                   # continuation of the DeltaEC header
    r'|^sameas\b',                 # cross-segment reference (no local value)
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Column splitter
# ---------------------------------------------------------------------------

def _split_columns(line: str):
    """
    Split a DeltaEC property line into (left_col, right_col).

    Right-column output values always start with a digit or sign and are
    preceded by a run of 4+ spaces that begins after column 30.
    """
    right_start = None
    for m in re.finditer(r' {4,}', line[30:]):
        candidate = 30 + m.end()
        rest = line[candidate:].lstrip()
        if rest and (rest[0].isdigit() or rest[0] in '+-'):
            right_start = candidate
            break
    if right_start is None:
        return line, ''
    return line[:right_start].rstrip(), line[right_start:].strip()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class DeltaECFile:
    """
    Parsed representation of a DeltaEC .out / .sp file.

    Attributes
    ----------
    path     : str
    segments : dict[int, Segment]   keyed by segment number (0 = BEGIN)
    begin    : Segment              convenience alias for segments[0]
    """

    def __init__(self, path: str):
        self.path = path
        self.segments: dict[int, Segment] = {}
        self.begin: Optional[Segment] = None
        self._pending_num = 0
        self._parse(path)

    # ------------------------------------------------------------------ API

    def get(self, seg_num: int, letter: str) -> float:
        """
        Return the numeric value of a property.

        Parameters
        ----------
        seg_num : int   Segment number (0 = BEGIN).
        letter  : str   'a'–'z' for inputs, 'A'–'Z' for outputs.

        Raises
        ------
        KeyError  segment or letter not found.
        """
        return self._req_prop(seg_num, letter).value

    def get_full(self, seg_num: int, letter: str):
        """
        Return ``(value, label, units)`` for a property.

        Returns
        -------
        tuple[float, str, str]
        """
        p = self._req_prop(seg_num, letter)
        return p.value, p.label, p.units

    def get_property(self, seg_num: int, letter: str) -> Property:
        """Return the full :class:`Property` object."""
        return self._req_prop(seg_num, letter)

    def segment_numbers(self) -> list:
        """Sorted list of all segment numbers present in the file."""
        return sorted(self.segments.keys())

    def dump_segment(self, seg_num: int, *, show_flags: bool = False):
        """Pretty-print all parsed properties for a segment."""
        seg = self._req_seg(seg_num)
        print(f"\nSegment {seg_num:>3}: {seg.seg_type}  —  {seg.name}")
        if seg.inputs:
            print("  Inputs:")
            for l in sorted(seg.inputs):
                p = seg.inputs[l]
                fs = f"  [{p.flags}]" if show_flags and p.flags.strip() else ""
                print(f"    {l}  {p.value:>14g}  {p.units:<8}  {p.label}{fs}")
        if seg.outputs:
            print("  Outputs:")
            for l in sorted(seg.outputs):
                p = seg.outputs[l]
                print(f"    {l}  {p.value:>14g}  {p.units:<8}  {p.label}")

    # ------------------------------------------------------------ internals

    def _req_seg(self, n: int) -> Segment:
        if n not in self.segments:
            raise KeyError(
                f"Segment {n} not found. Available: {self.segment_numbers()}"
            )
        return self.segments[n]

    def _req_prop(self, n: int, letter: str) -> Property:
        seg = self._req_seg(n)
        p = seg.get_property(letter)
        if p is None:
            avail = sorted(list(seg.inputs) + list(seg.outputs))
            raise KeyError(
                f"Letter '{letter}' not found in segment {n} "
                f"({seg.seg_type} '{seg.name}'). Available: {avail}"
            )
        return p

    def _parse(self, path: str):
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()

        current: Optional[Segment] = None
        expect_type = False

        for raw in lines:
            line = raw.rstrip('\n')

            # --- trailer: stop here ---
            if line.startswith('! The restart'):
                break
            if any(line.startswith(kw) for kw in
                   ('guessz', 'xprecn', 'targs', 'hilite', 'mstr-slave')):
                break

            # --- segment header comment ---
            m = _RE_SEG_HEADER.match(line)
            if m:
                current = None
                expect_type = True
                self._pending_num = int(m.group(1))
                continue

            # --- type / name line ---
            if expect_type and not line.startswith('!') and line.strip():
                m2 = _RE_TYPE_LINE.match(line)
                if m2:
                    stype = m2.group(1)
                    sname = m2.group(2).strip()
                    snum  = 0 if stype == 'BEGIN' else self._pending_num
                    current = Segment(number=snum, seg_type=stype, name=sname)
                    self.segments[snum] = current
                    if stype == 'BEGIN':
                        self.begin = current
                expect_type = False
                continue

            if current is None:
                continue

            # --- split the line into left and right columns ---
            left, right = _split_columns(line)

            # Left column: skip material/gas/RPN lines but still parse right
            if left and not _RE_LEFT_SKIP.match(left):
                self._parse_left(left, current)

            # Right column: always attempt to parse
            if right:
                self._parse_right(right, current)

    def _parse_left(self, text: str, seg: Segment):
        t = text.strip()
        if t.lower().startswith('sameas'):
            return
        m = _RE_INPUT.match(t)
        if not m:
            return
        raw, letter, label = m.group(1), m.group(2), m.group(3)
        units = m.group(4) or ''
        flags = (m.group(5) or '').strip()
        try:
            value = float(raw)
        except ValueError:
            return
        seg.inputs[letter] = Property(letter, value, label, units, flags, False)

    def _parse_right(self, text: str, seg: Segment):
        for m in _RE_OUTPUT.finditer(text):
            try:
                value = float(m.group(1))
            except ValueError:
                continue
            letter = m.group(2)
            label  = m.group(3)
            units  = m.group(4) or ''
            seg.outputs[letter] = Property(letter, value, label, units, '', True)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'new_00_.out'
    dec = DeltaECFile(path)

    print(f"Parsed {len(dec.segments)} segments: {dec.segment_numbers()}\n")
    dec.dump_segment(0)
    dec.dump_segment(14)
    dec.dump_segment(15)

    print("\n--- Example get() calls ---")
    # examples = [
    #     (0,  'b', "Frequency"),
    #     (0,  'c', "TBeg"),
    #     (14, 'c', "Regen length"),
    #     (14, 'F', "Regen Edot out"),
    #     (14, 'G', "Regen TBeg"),
    #     (14, 'H', "Regen TEnd"),
    #     (15, 'e', "HHX heat input"),
    #     (15, 'H', "HHX solid T (output)"),
    #     (10, 'I', "SOFTEND T"),
    #     (20, 'F', "UNION Edot"),
    #     (12, 'H', "CHX solid T"),
    # ]
    examples = [
        (0,  'b'),
        (0,  'c'),
        (14, 'c'),
        (14, 'F'),
        (14, 'G'),
        (14, 'H'),
        (15, 'e'),
        (15, 'H'),
        (10, 'I'),
        (20, 'F'),
        (12, 'H'),
    ]
    for sn, lt in examples:
        try:
            val, label, units = dec.get_full(sn, lt)
            print(f"  Seg {sn:>2d} {lt}  {val:>14g}  {label} [{units}]")
        except KeyError as e:
            print(f"  *** {e}")
