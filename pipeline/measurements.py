"""Pure numeric parsing for PSI source cells, preserving measurement qualifiers.

A source cell such as "< 0.1", "~ 21.5", "22.1 to 22.0" or "037 mm" carries more
information than a float does. Collapsing it to a float silently turns a detection
limit into an exact reading and a range into its first endpoint. This module keeps
the qualifier, the unit and both endpoints so that downstream code can decide what
is admissible for a given analysis.

No I/O and no dependency on the rest of the pipeline: importing this module runs
nothing. Tested in pipeline/test_measurements.py.

parse(text) -> Measurement with:
  raw       original text, stripped
  value     representative number, or None for intervals and unparseable text
  operator  "", "<", ">", "<=", ">=", "~"
  kind      "exact" | "approximate" | "censored" | "interval" | "empty" | "unparseable"
  lower     lower endpoint when known
  upper     upper endpoint when known
  unit      unit string when it can be identified without ambiguity, else ""

Censored values ("<", ">", "<=", ">=") are bounds, not measurements: `is_exact` is
False for them, so callers must opt in explicitly before using them in a fit.
"""

import re
from dataclasses import dataclass, asdict, field

__all__ = ["Measurement", "parse", "parse_number", "KINDS", "UNITS"]

KINDS = ("exact", "approximate", "censored", "interval", "empty", "unparseable")

# Units seen in the PSI tables. Longest first so "cm/s" wins over "cm" and
# "mm2/s" over "mm". Keys are matched case-insensitively against the trailing
# text of a cell; the value is the canonical spelling that gets stored.
UNITS = [
    ("mm2/s", "mm^2/s"), ("mm^2/s", "mm^2/s"), ("mm²/s", "mm^2/s"),
    ("cm/s", "cm/s"), ("mm/s", "mm/s"), ("m/s", "m/s"),
    ("mg/min", "mg/min"), ("mg/s", "mg/s"), ("sccm", "sccm"),
    ("mmhg", "mmHg"), ("torr", "torr"), ("kpa", "kPa"), ("psia", "psia"),
    ("psi", "psi"), ("atm", "atm"), ("bar", "bar"),
    ("micron", "um"), ("microns", "um"), ("um", "um"), ("µm", "um"),
    ("mm", "mm"), ("cm", "cm"), ("m", "m"),
    ("sec", "s"), ("s", "s"), ("min", "min"),
    ("deg c", "C"), ("degc", "C"), ("°c", "C"), ("c", "C"), ("k", "K"),
    ("w", "W"), ("kv", "kV"), ("v", "V"),
    ("%", "%"), ("vol%", "%"), ("% by vol", "%"),
]

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_NUM_RE = re.compile(_NUM)

# Leading qualifier. Order matters: two-character operators before one.
_OPS = [
    ("<=", "<="), ("=<", "<="), ("≤", "<="),
    (">=", ">="), ("=>", ">="), ("≥", ">="),
    ("<", "<"), (">", ">"),
    ("~", "~"), ("≈", "~"), ("ca.", "~"), ("approx.", "~"), ("approx", "~"), ("about", "~"),
]

# Range separators, checked only between two numbers.
_RANGE_SEP = re.compile(
    r"(?<=[\d.])\s*(?:--|–|—|to|through|\.\.\.?|−|-)\s*(?=[-+]?[\d.])",
    re.IGNORECASE,
)

_NOT_A_NUMBER = re.compile(
    r"^(n/?a|none|nil|tbd|unknown|not\s+\w+|see\s+.+|insignificant|complete\w*|"
    r"accelerat\w*|yes|no|\?+|-+|—+)$",
    re.IGNORECASE,
)


@dataclass
class Measurement:
    raw: str = ""
    value: float = None
    operator: str = ""
    kind: str = "empty"
    lower: float = None
    upper: float = None
    unit: str = ""
    notes: list = field(default_factory=list)

    @property
    def is_exact(self):
        """True only for a plain measured number. Bounds and ranges are not exact."""
        return self.kind == "exact"

    @property
    def is_usable_number(self):
        """Exact or approximate: has one representative value a caller may plot."""
        return self.kind in ("exact", "approximate") and self.value is not None

    @property
    def is_censored(self):
        return self.kind == "censored"

    def midpoint(self):
        """Interval midpoint. Explicit, so no caller collapses a range by accident."""
        if self.lower is None or self.upper is None:
            return self.value
        return (self.lower + self.upper) / 2.0

    def as_dict(self):
        d = asdict(self)
        d.pop("notes", None)
        return d

    def __repr__(self):
        return (f"Measurement(raw={self.raw!r}, value={self.value!r}, op={self.operator!r}, "
                f"kind={self.kind!r}, lower={self.lower!r}, upper={self.upper!r}, unit={self.unit!r})")


def _f(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return None if v != v or v in (float("inf"), float("-inf")) else v


def _strip_unit(text):
    """Split trailing unit off a cell. Returns (remainder, canonical unit)."""
    t = text.strip()
    low = t.lower()
    for token, canon in UNITS:
        if low.endswith(token):
            head = t[: len(t) - len(token)].rstrip()
            # Only a unit if what precedes it ends in a digit or a closing bracket:
            # avoids reading the "s" of "Notes" or the "C" of "PMMA C" as a unit.
            if head and (head[-1].isdigit() or head[-1] in ".)]%"):
                return head, canon
            # A bare "%" directly after a number is handled above; a lone unit
            # with no number is not a measurement at all.
    return t, ""


def _normalize_separators(text):
    """Resolve the comma: decimal point, thousands separator, or neither.

    "1,5" is a decimal comma (-> "1.5"). "1,500" and "1,234,567" are thousands
    separators (-> "1500"), as is any comma appearing alongside a period. An
    unresolved comma is dropped rather than left to split the number in two,
    which is what turned "1,500" into 1.0.
    """
    if "," not in text:
        return text
    if text.count(",") == 1 and "." not in text:
        a, b = text.split(",")
        a_ok = a.strip().lstrip("+-").isdigit()
        b_ok = b.strip().isdigit()
        if a_ok and b_ok and len(b.strip()) != 3:
            return text.replace(",", ".")      # decimal comma
    return text.replace(",", "")               # thousands separator


def parse(text, *, correct_dropped_decimal=False):
    """Parse one source cell. Never raises.

    correct_dropped_decimal: when True, an integer written with a leading zero and
    no decimal point (the PSI SAFFIRE-II "037 mm" pattern) is read as 0.37 and a
    note is recorded. Off by default so the behaviour is always opted into
    explicitly at the call site.
    """
    if text is None:
        return Measurement(raw="", kind="empty")
    raw = str(text).strip()
    if not raw:
        return Measurement(raw="", kind="empty")

    m = Measurement(raw=raw)

    if _NOT_A_NUMBER.match(raw):
        m.kind = "unparseable"
        return m

    body, m.unit = _strip_unit(raw)
    body = _normalize_separators(body).strip()

    # Leading operator
    op = ""
    low = body.lower()
    for token, canon in _OPS:
        if low.startswith(token):
            op = canon
            body = body[len(token):].strip()
            break
    m.operator = op

    # Interval, e.g. "21.5-21.7", "22.1 to 22.0", "0.5 – 3"
    parts = _RANGE_SEP.split(body, maxsplit=1)
    if len(parts) == 2 and not op:
        a, b = _f(_first_num(parts[0])), _f(_first_num(parts[1]))
        if a is not None and b is not None:
            m.kind = "interval"
            m.lower, m.upper = (a, b) if a <= b else (b, a)
            m.value = None  # a range is not one number; use midpoint() deliberately
            return m

    nums = _NUM_RE.findall(body)
    if not nums:
        m.kind = "unparseable"
        return m

    v = _f(nums[0])
    if v is None:
        m.kind = "unparseable"
        return m

    # "037 mm" -> 0.37 mm: a dropped decimal point in the source.
    if correct_dropped_decimal and _is_dropped_decimal(nums[0]):
        corrected = v / (10 ** (len(nums[0].lstrip("+-")) - 1))
        m.notes.append(f"source wrote {nums[0]!r}; read as {corrected:g} (dropped decimal point)")
        v = corrected

    m.value = v
    if op in ("<", ">", "<=", ">="):
        m.kind = "censored"
        if op in ("<", "<="):
            m.upper = v
        else:
            m.lower = v
    elif op == "~":
        m.kind = "approximate"
        m.lower = m.upper = v
    else:
        m.kind = "exact"
        m.lower = m.upper = v
    return m


def _first_num(s):
    found = _NUM_RE.findall(s or "")
    return found[0] if found else ""


def _is_dropped_decimal(token):
    """"037" / "0127" -> True. "0", "0.37", "37" -> False."""
    t = token.lstrip("+-")
    return len(t) > 1 and t[0] == "0" and t.isdigit()


def parse_number(text, *, allow_censored=False, allow_approximate=True,
                 allow_interval=False, correct_dropped_decimal=False):
    """Back-compatible float accessor that refuses to launder a qualifier.

    Returns a float or None. By default an exact or approximate value comes back,
    a censored bound does not, and an interval does not. Pass the flags to opt in.
    """
    m = parse(text, correct_dropped_decimal=correct_dropped_decimal)
    if m.kind == "exact":
        return m.value
    if m.kind == "approximate":
        return m.value if allow_approximate else None
    if m.kind == "censored":
        return m.value if allow_censored else None
    if m.kind == "interval":
        return m.midpoint() if allow_interval else None
    return None
