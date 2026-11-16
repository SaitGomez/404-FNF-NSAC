"""Unit tests for the measurement parser (commit 4).

These test meaning, not just that a key exists: a bound must stay a bound, a range
must keep both endpoints, and a qualifier must survive parsing.
"""

from measurements import parse, parse_number


# ---------------------------------------------------------------- exact values
def test_plain_integer():
    m = parse("21")
    assert (m.kind, m.value, m.operator) == ("exact", 21.0, "")
    assert m.is_exact and m.is_usable_number


def test_plain_decimal_with_unit():
    m = parse("21.5 %")
    assert m.kind == "exact"
    assert m.value == 21.5
    assert m.unit == "%"


def test_negative_value_is_not_a_range():
    m = parse("-4 cm/s")
    assert m.kind == "exact"
    assert m.value == -4.0
    assert m.unit == "cm/s"


def test_scientific_notation():
    assert parse("1.2e-3").value == 0.0012


def test_decimal_comma():
    assert parse("1,5").value == 1.5


def test_thousands_comma_is_not_a_decimal():
    assert parse("1,500").value == 1500.0


# ---------------------------------------------------------------- approximate
def test_tilde_is_approximate_not_exact():
    m = parse("~21.5")
    assert m.kind == "approximate"
    assert m.operator == "~"
    assert m.value == 21.5
    assert not m.is_exact          # must not pass as a measured number
    assert m.is_usable_number      # but may still be plotted when opted in


def test_unicode_approx_sign_and_space():
    m = parse("≈ 20")
    assert m.kind == "approximate"
    assert m.value == 20.0


def test_approximate_zero_keeps_the_qualifier():
    m = parse("~ 0")
    assert m.kind == "approximate"
    assert m.value == 0.0


# ---------------------------------------------------------------- censored
def test_less_than_is_censored_with_upper_bound():
    m = parse("<0.1")
    assert m.kind == "censored"
    assert m.operator == "<"
    assert m.value == 0.1
    assert m.upper == 0.1 and m.lower is None
    assert not m.is_exact
    assert m.is_censored


def test_greater_than_is_censored_with_lower_bound():
    m = parse(">5")
    assert m.kind == "censored"
    assert m.operator == ">"
    assert m.lower == 5.0 and m.upper is None


def test_greater_or_equal_variants():
    for s in (">=30", "=>30", "≥30"):
        m = parse(s)
        assert m.operator == ">=", s
        assert m.kind == "censored", s


def test_less_or_equal_variants():
    for s in ("<=10.2", "=<10.2", "≤10.2"):
        m = parse(s)
        assert m.operator == "<=", s
        assert m.kind == "censored", s


def test_censored_is_excluded_from_plain_float_access():
    assert parse_number("<0.1") is None
    assert parse_number("<0.1", allow_censored=True) == 0.1


# ---------------------------------------------------------------- intervals
def test_hyphen_range_keeps_both_endpoints():
    m = parse("21.5-21.7")
    assert m.kind == "interval"
    assert m.lower == 21.5 and m.upper == 21.7
    assert m.value is None          # never silently the first endpoint


def test_en_dash_range():
    m = parse("21.5–21.7")
    assert m.kind == "interval"
    assert (m.lower, m.upper) == (21.5, 21.7)


def test_descending_range_is_ordered():
    m = parse("22.1 to 22.0")     # appears verbatim in the SAFFIRE-II table
    assert m.kind == "interval"
    assert m.lower == 22.0 and m.upper == 22.1


def test_range_with_unit():
    m = parse("0.5 - 3 atm")
    assert m.kind == "interval"
    assert (m.lower, m.upper) == (0.5, 3.0)
    assert m.unit == "atm"


def test_interval_midpoint_is_opt_in():
    m = parse("21.5-21.7")
    assert parse_number("21.5-21.7") is None
    assert abs(m.midpoint() - 21.6) < 1e-9
    assert abs(parse_number("21.5-21.7", allow_interval=True) - 21.6) < 1e-9


# ---------------------------------------------------------------- units
def test_unit_longest_match_wins():
    assert parse("20 cm/s").unit == "cm/s"
    assert parse("5 cm").unit == "cm"
    assert parse("0.4 mm2/s").unit == "mm^2/s"


def test_pressure_units():
    assert parse("760 mmHg").unit == "mmHg"
    assert parse("101.3 kPa").unit == "kPa"
    assert parse("8.2 psia").unit == "psia"


def test_unit_does_not_swallow_a_word():
    # "Notes" must not yield unit "s"
    m = parse("Notes")
    assert m.kind == "unparseable"
    assert m.unit == ""


# ---------------------------------------------------------------- non-numeric
def test_non_numeric_text_is_unparseable_not_zero():
    for s in ("n/a", "N/A", "none", "Insignificant", "Complete", "Acceleratory", "See Fig. 5", "?"):
        m = parse(s)
        assert m.kind == "unparseable", s
        assert m.value is None, s
        assert parse_number(s) is None, s


def test_empty_and_none():
    for s in ("", "   ", None):
        m = parse(s)
        assert m.kind == "empty"
        assert m.value is None


def test_raw_is_always_preserved():
    for s in ("<0.1", "~ 21.5", "22.1 to 22.0", "037 mm", "See Fig. 5"):
        assert parse(s).raw == s.strip()


# ---------------------------------------------------------------- dropped decimal
def test_dropped_decimal_is_off_by_default():
    m = parse("037 mm")
    assert m.value == 37.0
    assert m.notes == []


def test_dropped_decimal_correction_is_logged():
    m = parse("037 mm", correct_dropped_decimal=True)
    assert abs(m.value - 0.37) < 1e-12
    assert m.unit == "mm"
    assert m.notes and "dropped decimal" in m.notes[0]


def test_dropped_decimal_leaves_normal_numbers_alone():
    for s, want in (("0", 0.0), ("0.37", 0.37), ("37", 37.0), ("1", 1.0)):
        assert parse(s, correct_dropped_decimal=True).value == want, s


# ---------------------------------------------------------------- real source cells
def test_real_saffire_cells():
    cases = {
        "~ 21.5": ("approximate", 21.5),
        "22.1 to 22.0": ("interval", None),
        "20 cm/s": ("exact", 20.0),
        "0.27 mm": ("exact", 0.27),
        "1 cm": ("exact", 1.0),
    }
    for cell, (kind, value) in cases.items():
        m = parse(cell)
        assert m.kind == kind, cell
        assert m.value == value, cell
