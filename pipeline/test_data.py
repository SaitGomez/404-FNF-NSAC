"""Regression tests for the FlameBench data layer (commits 1-8).

These assert meaning, not the presence of keys: a record that is not an
individual test must not be plottable, a bound must not read as a measurement,
and a figure shown in the interface must come from the data rather than from
text typed into the app.

Run from the repository root:  python3 -m pytest pipeline/ -q
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "data.json"


def load_payload():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def load_rows():
    data = load_payload()
    fields = data["TF"]
    return data, [dict(zip(fields, values)) for values in data["tests"]]


@pytest.fixture(scope="module")
def payload():
    return load_payload()


@pytest.fixture(scope="module")
def rows():
    return load_rows()[1]


@pytest.fixture(scope="module")
def data_and_rows():
    return load_rows()


def investigation_id(data, row):
    return data["inv"][row["inv"]]["id"]


# ---------------------------------------------------------------- shape
def test_every_row_matches_the_field_list(payload):
    n = len(payload["TF"])
    assert payload["tests"], "no test rows in the bundle"
    assert all(len(r) == n for r in payload["tests"]), "row length does not match TF"


def test_total_row_count_is_unchanged(rows):
    # Correcting classification must not drop source rows.
    assert len(rows) == 2009


# ---------------------------------------------------------------- commit 2
def test_individual_test_count_after_reclassification(rows):
    assert sum(row["lvl"] == "test" for row in rows) == 1871


def test_ind_flag_agrees_with_level(rows):
    for row in rows:
        assert bool(row["ind"]) == (row["lvl"] == "test")


def test_saffire_visualizations_and_notes_are_not_tests(data_and_rows):
    data, rows = data_and_rows
    seen = {"visualization": 0, "note": 0}
    for row in rows:
        pid = investigation_id(data, row)
        tid = str(row["tid"])
        if pid in ("PSI-98", "PSI-99") and tid.startswith(("F1C1/", "F2C1/")):
            assert row["lvl"] == "visualization", tid
            seen["visualization"] += 1
        if pid == "PSI-99" and tid.startswith("Note "):
            assert row["lvl"] == "note", tid
            seen["note"] += 1
    # Two visualizations in SAFFIRE-I, two in SAFFIRE-II, four notes in SAFFIRE-II.
    assert seen == {"visualization": 4, "note": 4}


def test_non_individual_records_are_not_plot_eligible(rows):
    for row in rows:
        if row["lvl"] != "test":
            assert not row["plot"], f"{row['lvl']} row {row['tid']} is plot-eligible"


def test_reclassified_records_carry_no_outcome(rows):
    for row in rows:
        if row["lvl"] in ("visualization", "note", "dataset", "session"):
            assert not row["out"], f"{row['lvl']} row {row['tid']} has outcome {row['out']!r}"
            assert row["ign"] is None and row["ext"] is None


def test_reclassified_records_are_still_present_with_their_source_text(data_and_rows):
    data, rows = data_and_rows
    notes = [r for r in rows if r["lvl"] == "note"]
    assert len(notes) == 4
    # The footnote text is preserved so the record stays usable as documentation.
    assert all(str(r["tid"]).startswith("Note ") and len(str(r["tid"])) > 10 for r in notes)


def test_aggregates_are_not_counted_as_individual_tests(rows):
    aggregates = [r for r in rows if r["lvl"] in ("test-day summary", "campaign summary")]
    assert len(aggregates) == 120
    assert all(not r["ind"] for r in aggregates)


# ---------------------------------------------------------------- commit 3
def test_saffire2_materials_are_resolved_or_explicitly_unresolved(data_and_rows):
    data, rows = data_and_rows
    s2 = [r for r in rows
          if investigation_id(data, r) == "PSI-99" and r["lvl"] == "test"]
    assert len(s2) == 9
    for row in s2:
        assert row["fuel"], f"sample {row['tid']} has no material and no unresolved marker"


def test_saffire2_inherited_materials_are_traceable(data_and_rows):
    data, rows = data_and_rows
    by_tid = {str(r["tid"]): r for r in rows if investigation_id(data, r) == "PSI-99"}
    # 2-6 continues the SIBAL block, 2-9 continues the PMMA block.
    assert by_tid["2-6"]["matinh"] == 1
    assert by_tid["2-6"]["matsrc"] == "2-5"
    assert "SIBAL" in by_tid["2-6"]["fuel"]
    assert by_tid["2-9"]["matinh"] == 1
    assert by_tid["2-9"]["matsrc"] == "2-8"
    assert "PMMA" in by_tid["2-9"]["fuel"]
    # Rows that stated their own material are not marked as inherited.
    assert by_tid["2-5"]["matinh"] == 0
    assert by_tid["2-8"]["matinh"] == 0


def test_composite_material_is_not_reduced_to_a_pure_one(data_and_rows):
    data, rows = data_and_rows
    row = next(r for r in rows
               if investigation_id(data, r) == "PSI-99" and str(r["tid"]) == "2-7")
    assert row["fuel"] == "PMMA & Nomex"


# ---------------------------------------------------------------- commit 4
def test_measurement_kinds_are_recorded(rows):
    kinds = {r["o2k"] for r in rows if r["o2k"]}
    # The SAFFIRE tables contain approximate and interval O2 cells.
    assert "approximate" in kinds
    assert "interval" in kinds
    assert "exact" in kinds


def test_approximate_o2_cells_are_marked_not_laundered(data_and_rows):
    data, rows = data_and_rows
    approx = [r for r in rows if r["o2k"] == "approximate"]
    assert approx, "no approximate O2 cells found"
    for row in approx:
        assert row["o2raw"].lstrip().startswith(("~", "≈")), row["o2raw"]


def test_interval_o2_cells_keep_both_endpoints(rows):
    intervals = [r for r in rows if r["o2k"] == "interval"]
    assert intervals
    for row in intervals:
        assert row["o2a"] is not None and row["o2b"] is not None
        assert row["o2a"] <= row["o2b"]


# ---------------------------------------------------------------- commit 5
def test_signed_bass_flow_is_preserved(data_and_rows):
    data, rows = data_and_rows
    bass = [row for row in rows
            if investigation_id(data, row) == "PSI-26" and str(row["tid"]) in {"3", "7", "8", "10"}]
    assert len(bass) == 4
    assert all(row["flminr"] is not None and row["flminr"] < 0 for row in bass), \
        "the four negative BASS minimum flows must be recoverable"


def test_charted_flow_is_a_magnitude(data_and_rows):
    data, rows = data_and_rows
    for row in rows:
        for key in ("fla", "flb"):
            if row[key] is not None:
                assert row[key] >= 0, f"{key} must be a magnitude, got {row[key]}"


def test_negative_scalar_flow_is_flagged_not_silently_dropped(rows):
    flagged = [r for r in rows if r["qa"] == "flow_invalid"]
    assert len(flagged) == 8
    for row in flagged:
        assert row["qfl"] == 0, "flow quality must be marked invalid"
        assert row["flmaxr"] is not None, "the signed original must survive"


# ---------------------------------------------------------------- commit 6
def test_bass2_keeps_initial_and_final_oxygen_apart(data_and_rows):
    data, rows = data_and_rows
    b2 = [r for r in rows if investigation_id(data, r) == "PSI-25"]
    with_final = [r for r in b2 if r["o2f"] is not None]
    assert len(with_final) >= 120, "final O2 must be preserved as its own field"
    # At least one row where the two genuinely differ, proving they are not copies.
    assert any(r["o2i"] is not None and r["o2f"] is not None and r["o2i"] != r["o2f"]
               for r in b2)


def test_anomalous_final_oxygen_is_flagged_but_kept(data_and_rows):
    data, rows = data_and_rows
    bad = [r for r in rows if r["o2f"] is not None and r["o2fv"] == 0]
    assert bad, "the anomalous final-O2 rows should be flagged"
    for row in bad:
        assert row["o2f"] is not None, "a flagged value must still be recoverable"


def test_investigations_without_final_oxygen_do_not_borrow_it(data_and_rows):
    data, rows = data_and_rows
    for row in rows:
        if investigation_id(data, row) != "PSI-25":
            assert row["o2f"] is None, \
                f"{investigation_id(data, row)} must not have a final-O2 value"


# ---------------------------------------------------------------- commit 7
def test_pressure_provenance_has_three_states(rows):
    states = {row["pstate"] for row in rows}
    assert states == {"measured", "assumed", "no_data"}


def test_pressure_state_counts(rows):
    counts = {}
    for row in rows:
        counts[row["pstate"]] = counts.get(row["pstate"], 0) + 1
    # 812 assumed in the original data, minus the 8 reclassified SAFFIRE records
    # that no longer receive the cabin-pressure assumption.
    assert counts["assumed"] == 804
    assert counts["no_data"] == 76
    assert sum(counts.values()) == 2009


def test_no_data_rows_have_no_pressure_number(rows):
    for row in rows:
        if row["pstate"] == "no_data":
            assert row["p"] is None
        else:
            assert row["p"] is not None


def test_assumed_pressure_is_flagged_and_equals_cabin_pressure(rows):
    for row in rows:
        if row["pstate"] == "assumed":
            assert row["pas"] == 1
            assert row["p"] == 101.3
        if row["pstate"] == "measured":
            assert row["pas"] == 0


# ---------------------------------------------------------------- commit 8
def test_every_row_has_per_variable_quality_flags(rows):
    for row in rows:
        for key in ("qo2", "qp", "qfl", "qout"):
            assert row[key] in (0, 1), f"{key} must be 0 or 1"


def test_a_flow_flag_does_not_void_oxygen_or_pressure(rows):
    """The point of per-variable quality: one bad column keeps the rest usable."""
    flagged = [r for r in rows if r["qa"] == "flow_invalid"]
    assert flagged
    assert any(r["qo2"] == 1 and r["o2b"] is not None for r in flagged), \
        "rows with an invalid flow should still offer usable oxygen"


def test_invalid_oxygen_rows_are_marked(rows):
    bad = [r for r in rows if r["qa"] == "o2_invalid"]
    assert len(bad) == 2
    for row in bad:
        assert row["qo2"] == 0
        assert row["o2b"] is None


def test_quality_flag_counts_are_unchanged(rows):
    counts = {}
    for row in rows:
        if row["qa"]:
            counts[row["qa"]] = counts.get(row["qa"], 0) + 1
    assert counts == {"source_anomaly": 11, "flow_invalid": 8, "o2_invalid": 2, "o2_corrected": 2}


# ---------------------------------------------------------------- commit 9 / 13 inputs
def test_outcome_raw_codes_are_stable_and_english(rows):
    codes = {r["outr"] for r in rows if r["outr"]}
    expected = {"burned", "extinguished", "flow reduced to extinction", "no ignition",
                "no sustained burning", "self-extinguished", "flow terminated", "ignited",
                "extinction", "disruption", "completion"}
    assert codes <= expected, f"unexpected outcome codes: {codes - expected}"


def test_flow_reduced_to_extinction_figure_comes_from_the_data(rows):
    """Module C must not hard-code 22 %: the data tops out at 20.9 %."""
    q = [r for r in rows if r["outr"] == "flow reduced to extinction"]
    assert len(q) == 16
    o2 = [r["o2b"] for r in q if r["o2b"] is not None]
    assert abs(max(o2) - 20.9) < 1e-9, f"maximum O2 is {max(o2)}, not 22"


def test_solid_map_points_all_have_a_recorded_outcome_or_are_marked(data_and_rows):
    """Commit 9: a point with no outcome must be identifiable as such."""
    data, rows = data_and_rows
    pts = [r for r in rows if r["st"] == "solid" and r["plot"]
           and r["o2b"] is not None and r["flb"] is not None]
    assert pts
    unknown = [r for r in pts if not r["outr"]]
    # They still exist in the data; the app must render them as "unknown".
    assert all(r["qout"] == 0 for r in unknown)
    assert all(r["qout"] == 1 for r in pts if r["outr"])


def test_max_solid_oxygen_is_below_exploration_atmosphere(rows):
    """The headline data gap: no solid test reaches the 34 % lunar atmosphere."""
    o2 = [r["o2b"] for r in rows if r["st"] == "solid" and r["o2b"] is not None]
    assert max(o2) < 30


# ---------------------------------------------------------------- investigations
def test_investigation_counts_separate_individual_from_total(payload):
    for v in payload["inv"]:
        assert v["nind"] <= v["n"]
    saffire2 = next(v for v in payload["inv"] if v["id"] == "PSI-99")
    assert (saffire2["nind"], saffire2["n"]) == (9, 15)
    saffire1 = next(v for v in payload["inv"] if v["id"] == "PSI-98")
    assert (saffire1["nind"], saffire1["n"]) == (2, 4)


def test_investigation_ranges_use_individual_tests_only(payload):
    saffire2 = next(v for v in payload["inv"] if v["id"] == "PSI-99")
    assert saffire2["o2"] == [21.5, 22.1]


def test_every_investigation_has_a_doi(payload):
    for v in payload["inv"]:
        assert v["doi"], f"{v['id']} has no DOI"


# ---------------------------------------------------------------- commit 17
def test_temporal_claims_carry_a_status_and_a_check_date(payload):
    for x in payload["ext"]:
        assert x.get("status"), f"external evidence {x['id']} has no status"
        assert x.get("checked"), f"external evidence {x['id']} has no check date"


def test_fm2_is_not_described_as_already_performed(payload):
    fm2 = next(x for x in payload["ext"] if x["id"] == "fm2")
    status = fm2["status"].lower()
    assert "planned" in status
    assert "not flown" in status or "no results" in status


def test_sofie_separates_operation_from_published_results(payload):
    sofie = next(x for x in payload["ext"] if x["id"] == "sofie")
    status = sofie["status"].lower()
    assert "operating" in status
    assert "planned" in status or "to come" in status
