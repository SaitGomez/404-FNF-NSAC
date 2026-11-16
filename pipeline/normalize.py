"""Normalize PSI combustion experimental tables into one test-level table.

Usage: python3 -I normalize.py <psi_dir>
Reads <psi_dir>/tables/*.csv and <psi_dir>/metadata/PSI-*.json
Writes <psi_dir>/clean/tests.csv, tests.json, investigations.csv, investigations.json

Record classification (one definition, used by the whole pipeline):
  test              one individual experimental run; may become a plotted point
  test-day summary  aggregate over a test day; never an individual point
  campaign summary  aggregate over a campaign; never an individual point
  dataset, session  metadata; not experimental runs
  note              documentary footnote carried in the source table
  visualization     pre-test flow-visualisation record, not a burn test

Only `level == "test"` rows are individual tests. Notes and visualizations are
kept with their source text and row number so they stay available as
documentation, but they are not counted as tests and are not plotted.

Measurement provenance: every numeric column that carries a qualifier in the
source ("<", ">", "~", a range) also gets a *_raw column with the original text
and a *_kind column from pipeline/measurements.py, so a bound is never used as
if it were an exact reading.
"""
import csv, io, json, re, os, sys, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measurements import parse as mparse

BASE = sys.argv[1]
OUT = os.path.join(BASE, "clean")
os.makedirs(OUT, exist_ok=True)

NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

# Levels that represent one individual experimental run.
INDIVIDUAL_LEVELS = {"test"}
# Levels that are aggregates of several runs.
AGGREGATE_LEVELS = {"test-day summary", "campaign summary"}
# Levels that are not experimental data at all.
NON_EXPERIMENTAL_LEVELS = {"dataset", "session", "note", "visualization"}


def is_individual(level):
    return level in INDIVIDUAL_LEVELS


# The SAFFIRE-I table heads its thickness column "(cm)" and gives 0.37 for SIBAL
# fabric. Two independent sources contradict that unit: the SAFFIRE-II table
# gives "037 mm" (0.37 mm) for the same cotton/fibreglass fabric, and the NASA
# Saffire sample layout (NTRS 20150000894) gives 0.33 mm for SIBAL cloth in
# Saffire I/III. Reading the column as centimetres yields 3.7 mm, a tenfold
# disagreement with both. The column is therefore read as millimetres and the
# row is marked so the choice stays visible and reversible.
SAFFIRE1_THICKNESS_UNIT_IS_MM = True


def saffire_level(test_id, material):
    """Classify a SAFFIRE table row (commit 2).

    The SAFFIRE-I and SAFFIRE-II tables carry three kinds of row under one
    header: burn tests, pre-test flow-visualisation records whose Sample Number
    is an image-pair id (F1C1/F1C2), and footnotes whose Sample Number holds the
    whole note text. Only the first kind is a test.
    """
    tid = (test_id or "").strip()
    mat = (material or "").strip().lower()
    if re.match(r"^note\s+\d", tid, re.IGNORECASE):
        return "note"
    if re.match(r"^F\d+C\d+\s*/", tid, re.IGNORECASE) or "visulation" in mat or "visualisation" in mat or "visualization" in mat:
        return "visualization"
    return "test"


def nums(s):
    if s is None:
        return []
    s = str(s).replace(",", ".") if str(s).count(",") == 1 and "." not in str(s) else str(s)
    return [float(x) for x in NUM.findall(s)]


def first(s):
    n = nums(s)
    return n[0] if n else None


def rng(s):
    n = nums(s)
    return (min(n), max(n)) if n else (None, None)


def read(name):
    p = os.path.join(BASE, "tables", name)
    txt = open(p, encoding="utf-8", errors="replace").read()
    rows = [r for r in csv.reader(io.StringIO(txt)) if any(c.strip() for c in r)]
    hdr = [re.sub(r"\s+", " ", h).strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        r = r + [""] * (len(hdr) - len(r))
        out.append({h: (v.strip() if isinstance(v, str) else v) for h, v in zip(hdr, r)})
    return out


FIELDS = [
    "psi_id", "acronym", "source_table", "row_in_source", "test_id", "date", "level",
    "is_individual_test",
    "fuel_state", "fuel", "geometry", "thickness_mm", "o2_pct_min", "o2_pct_max",
    "pressure_kpa", "diluent", "flow_cm_s_min", "flow_cm_s", "flow_dir", "gravity", "outcome",
    "burn_time_s", "spread_rate_mm_s", "burn_length_cm", "burn_length_1g", "spread_rate_1g",
    "extinction_diam_mm", "droplet_d0_mm", "n_flames", "qa_flag", "notes",
    # --- provenance added by the correction pass -------------------------------
    "fuel_raw", "material_inherited", "material_source_row", "material_unresolved",
    "o2_initial_pct", "o2_final_pct", "o2_final_valid",
    "o2_raw", "o2_kind", "pressure_raw", "pressure_kind", "pressure_source",
    "thickness_raw", "thickness_kind",
    "flow_cm_s_raw", "flow_cm_s_min_raw", "flow_cm_s_kind", "flow_valid",
]

# Columns whose value is a number with a qualifier worth keeping.
tests = []


def add(**kw):
    row = {k: kw.get(k) for k in FIELDS}
    row.setdefault("gravity", "microgravity")
    if row["gravity"] is None:
        row["gravity"] = "microgravity"
    if row["level"] is None:
        row["level"] = "test"
    row["is_individual_test"] = 1 if is_individual(row["level"]) else 0
    # A record that is not an individual test carries no outcome of its own.
    if not row["is_individual_test"] and row["level"] in NON_EXPERIMENTAL_LEVELS:
        row["outcome"] = None
    tests.append(row)


def prov(row, field, text, *, correct_dropped_decimal=False, kind_only=False):
    """Record the raw text and kind of one measurement on a row dict.

    kind_only: record just the qualifier kind. Used for flow, where the signed
    numeric originals already live in flow_cm_s_raw / flow_cm_s_min_raw and the
    raw cell is a composite display string.
    """
    m = mparse(text, correct_dropped_decimal=correct_dropped_decimal)
    if not kind_only:
        row[field + "_raw"] = m.raw or None
    row[field + "_kind"] = m.kind if m.raw else None
    return m


def solid_geom(mat):
    m = (mat or "").lower()
    if "sphere" in m or "spher" in m:
        return "sphere"
    if "rod" in m or "cylinder" in m:
        return "rod"
    if "fabric" in m or "sibal" in m or "cloth" in m or "nomex" in m or "cotton" in m:
        return "fabric"
    if "film" in m or "micron" in m or "slab" in m or "sheet" in m or "mm" in m:
        return "sheet"
    return None


def thick_from_text(mat):
    m = (mat or "").lower()
    mu = re.search(r"(\d+)\s*micron", m)
    if mu:
        return float(mu.group(1)) / 1000
    mm = re.search(r"(\d*\.?\d+)\s*mm", m)
    if mm:
        return float(mm.group(1))
    return None


# ---------- SAFFIRE ----------
for i, r in enumerate(read("PSI-98_Experimental table_SAFFIRE-1.csv"), 1):
    lvl = saffire_level(r["Sample Number"], r["Material"])
    o2cell = r.get("Percent O2")
    lo, hi = rng(o2cell)
    _th1 = first(r["Sample Thickness (cm)"])
    _thick1 = (_th1 if SAFFIRE1_THICKNESS_UNIT_IS_MM else _th1 * 10) if _th1 else None
    row = dict(psi_id="PSI-98", acronym="SAFFIRE-I", source_table="SAFFIRE-1", row_in_source=i, test_id=r["Sample Number"],
               level=lvl, fuel_state="solid", fuel=r["Material"], fuel_raw=r["Material"], geometry="fabric",
               thickness_mm=_thick1,
               o2_pct_min=lo, o2_pct_max=hi, pressure_kpa=None, pressure_source="",
               flow_cm_s=first(r["Air Flow (cm/s)"]), flow_dir=r["Flow Direction"].strip().lower(),
               burn_time_s=first(r["Burn Time (s)"]),
               # Only a real burn test has an outcome; `add` clears it otherwise.
               outcome="burned" if lvl == "test" else None,
               notes=("Cygnus, large-scale sample 40.6 x 94 cm" if lvl == "test"
                      else f"non-experimental record kept as documentation ({lvl}); source text: {r['Material'][:120]}"))
    prov(row, "o2", o2cell)
    prov(row, "flow_cm_s", r.get("Air Flow (cm/s)"), kind_only=True)
    prov(row, "thickness", r.get("Sample Thickness (cm)"))
    if _thick1 is not None and SAFFIRE1_THICKNESS_UNIT_IS_MM:
        row["notes"] += (f" | QA: source thickness column headed '(cm)' with value {_th1:g}; read as "
                         f"{_thick1:g} mm to agree with the SAFFIRE-II table (0.37 mm) and the NASA "
                         f"Saffire sample layout (0.33 mm, NTRS 20150000894)")
    add(**row)

# SAFFIRE-II: material is left blank on continuation rows. The NASA sample layout
# for Saffire II (NTRS 20150000894) lists samples 5 and 6 as "SIBAL fabric 1" and
# "SIBAL fabric 2", and samples 8 and 9 as "Structured PMMA" and "Flat PMMA", so
# inheriting the material downward from the preceding row is supported by the
# source for both blanks rather than guessed. Inheritance is recorded, never silent.
SAFFIRE2_INHERIT_SOURCE = {"2-6": "2-5", "2-9": "2-8"}
_s2_prev = {"tid": None, "fuel": None}
for i, r in enumerate(read("PSI-99_Experimental table_SAFFIRE-2.csv"), 1):
    tid = (r["Sample Number"] or "").strip()
    lvl = saffire_level(tid, r["Material"])
    o2cell = r.get("Percent O2 (Note 1)")
    lo, hi = rng(o2cell)
    bl = r.get("?-g Burn Length", "")
    ign = (r.get("Burn Time (s)", "") or "").lower()
    outcome = "no sustained burning" if ("insignificant" in ign or bl.strip().startswith("~ 0")) else "burned"
    th = r.get("Samle Thickness", "")

    fuel_raw = (r["Material"] or "").strip()
    fuel = fuel_raw
    inherited, src_row, unresolved = 0, None, 0
    if lvl == "test" and not fuel:
        want = SAFFIRE2_INHERIT_SOURCE.get(tid)
        if want and _s2_prev["tid"] == want and _s2_prev["fuel"]:
            fuel, inherited, src_row = _s2_prev["fuel"], 1, want
        else:
            unresolved = 1          # ambiguous: leave blank rather than guess
    if lvl == "test" and fuel:
        _s2_prev = {"tid": tid, "fuel": fuel if not inherited else _s2_prev["fuel"]}

    # "037 mm" in this table is a dropped decimal point: the NASA sample layout
    # gives 0.36 mm for the silicone downward-burn sample and 0.33 mm for SIBAL.
    tm = mparse(th, correct_dropped_decimal=True)
    thick = tm.value * (10 if "cm" in (th or "").lower() else 1) if tm.value is not None else None

    row = dict(psi_id="PSI-99", acronym="SAFFIRE-II", source_table="SAFFIRE-2", row_in_source=i, test_id=tid,
               level=lvl, fuel_state="solid", fuel=fuel or None, fuel_raw=fuel_raw or None,
               material_inherited=inherited, material_source_row=src_row,
               material_unresolved=unresolved,
               geometry=solid_geom(fuel) or ("sheet" if lvl == "test" else None),
               thickness_mm=round(thick, 4) if thick is not None else None,
               o2_pct_min=lo, o2_pct_max=hi,
               flow_cm_s=first(r["Air Flow (cm/s)"]), flow_dir=r["Flow Direction"].strip().lower(),
               burn_time_s=first(r["Burn Time (s)"]),
               outcome=outcome if lvl == "test" else None,
               burn_length_cm=bl if lvl == "test" else None,
               spread_rate_mm_s=None,
               burn_length_1g=r.get("1-g Burn Length") if lvl == "test" else None,
               spread_rate_1g=r.get("1-g Spread Rate") if lvl == "test" else None,
               pressure_source="",
               notes=(f"ug spread length: {r.get('?-g Spread Length','')}" if lvl == "test"
                      else f"non-experimental record kept as documentation ({lvl}); source text: {tid[:160]}"))
    if inherited:
        row["notes"] += f" | material inherited from row {src_row} (NASA Saffire II sample layout, NTRS 20150000894)"
    if unresolved:
        row["notes"] += " | material not stated in source and continuity not confirmed; left unresolved"
    prov(row, "o2", o2cell)
    prov(row, "flow_cm_s", r.get("Air Flow (cm/s)"), kind_only=True)
    row["thickness_raw"] = tm.raw or None
    row["thickness_kind"] = tm.kind if tm.raw else None
    if tm.notes:
        row["notes"] += " | QA: thickness " + "; ".join(tm.notes)
    add(**row)

for i, r in enumerate(read("PSI-100_Experimental table_SAFFIRE-3.csv"), 1):
    th = r.get("Sample Thickness", "")
    add(psi_id="PSI-100", acronym="SAFFIRE-III", source_table="SAFFIRE-3", row_in_source=i, test_id=r["Sample Number"],
        level="test", fuel_state="solid", fuel=r["Material"], geometry="fabric",
        thickness_mm=first(th) * 10 if first(th) is not None else None,
        flow_cm_s=first(r["Air Flow"]), flow_dir=r["Direction"].strip().lower(), outcome="burned",
        notes="Cygnus, large-scale sample; O2 not given in table (cabin ~21%)")

# ---------- BASS / BASS-II ----------
for i, r in enumerate(read("PSI-25_Experimental table_BASS-II.csv"), 1):
    mat = re.sub(r"\s+", " ", r["Fuel Sample Material"])
    o2i_cell = r["Calibrated initial O2 % by vol"]
    o2f_cell = r["Calibrated final O2 % by vol"]
    o2i, o2f = first(o2i_cell), first(o2f_cell)
    # Final O2 is a measured column of its own (commit 6). It is kept as its own
    # field with a validity flag instead of being folded into `notes`; the
    # flammability boundary of the BASS-II report is a function of final O2, so
    # initial O2 must never silently stand in for it.
    o2f_valid = 1 if o2f is not None else 0
    flag = ""
    if o2f is not None and o2i is not None and o2f > o2i + 3:
        o2f_valid = 0
        flag = f" | ANOMALY: final O2 {o2f}% > initial {o2i}% (source data issue, final flagged invalid but preserved)"
    if "ext" in (r["Fan display"] or ""):
        flag += " | ANOMALY: columns appear shifted in source row"
    pi = r["PI"].strip()
    fdir = {"Olson": "concurrent (stagnation, upstream ignition)", "Fernandez-Pello": "opposed",
            "Bhattacharjee": "opposed", "Miller": "opposed", "T'ien": "concurrent", "Ferkul": None}.get(pi)
    air = r["Air display"] or ""
    fl = [v for v in nums(air) if v <= 45] if "pot" not in air else []
    ext = "ext" in (air + " " + (r["Fan display"] or "")).lower()
    row = dict(psi_id="PSI-25", acronym="BASS-II", source_table="BASS-II", row_in_source=i, test_id=r["Test #"], date=r["Date"],
               level="test", fuel_state="solid", fuel=mat, fuel_raw=mat, geometry=solid_geom(mat),
               thickness_mm=thick_from_text(mat),
               o2_pct_min=o2i, o2_pct_max=o2i,
               o2_initial_pct=o2i, o2_final_pct=o2f, o2_final_valid=o2f_valid,
               flow_dir=fdir, pressure_source="",
               flow_cm_s_min=min(fl) if fl else None, flow_cm_s=max(fl) if fl else None,
               outcome="flow reduced to extinction" if ext else None,
               notes=(f"PI {r['PI']}; O2 min/max = calibrated initial; fan display {r['Fan display']}; "
                      f"air display {r['Air display']}; flow restrictor {r['Flow restrictor']}{flag}"))
    prov(row, "o2", o2i_cell)
    prov(row, "flow_cm_s", air, kind_only=True)
    add(**row)

# BASS as-run matrix (Science Documents xlsx) adds O2, pressure, air speed and crew observations
asrun = {}
_xl = os.path.join(BASE, "documents", "PSI-26", "PSI-26_Science Documents_As Run_Test Matrix.xlsx")
if os.path.exists(_xl):
    import openpyxl, warnings
    warnings.filterwarnings("ignore")
    ws = openpyxl.load_workbook(_xl, data_only=True)["as run matrix"]
    rows_ = list(ws.iter_rows(values_only=True))
    hdr = [re.sub(r"\s+", " ", str(h or "")).strip() for h in rows_[2]]
    for rr in rows_[3:]:
        d = dict(zip(hdr, rr))
        k = d.get("As run test no.")
        if k is not None:
            asrun[str(k).strip()] = d
for i, r in enumerate(read("PSI-26_Experimental table_BASS.csv"), 1):
    mat = r["Fuel Sample Material"]
    a = asrun.get(str(r["As Run Test #"]).strip(), {})
    o2 = a.get("O2 % by volume")
    o2 = o2 * 100 if isinstance(o2, (int, float)) and o2 <= 1 else (o2 if isinstance(o2, (int, float)) else None)
    pa = a.get("pressure, atm")
    air = str(a.get("Air display") or "")
    fl = [v for v in nums(air) if v <= 45] if "pot" not in air else []
    obs = str(a.get("Test Observations and Anomalies (ignited, spread, extinguished, burn time, color, etc.)") or "")
    ol = obs.lower()
    outcome = "no ignition" if "no ignition" in ol else ("extinguished" if ("extinguish" in ol or " ext" in ol or "blow" in ol) else ("burned" if obs else None))
    pkpa = round(pa * 101.325, 1) if isinstance(pa, (int, float)) else None
    row = dict(psi_id="PSI-26", acronym="BASS", source_table="BASS + as-run matrix", row_in_source=i, test_id=r["As Run Test #"], date=r["Date"],
               level="test", fuel_state="solid", fuel=mat, fuel_raw=mat, geometry=solid_geom(mat),
               thickness_mm=thick_from_text(mat),
               o2_pct_min=o2, o2_pct_max=o2, pressure_kpa=pkpa,
               # Pressure here is read from the As Run matrix, so it is measured.
               pressure_source="measured" if pkpa is not None else "",
               flow_cm_s_min=min(fl) if fl else None, flow_cm_s=max(fl) if fl else None, outcome=outcome,
               notes=(f"planned test #{r['Test #']}, sample #{r['Sample #']}; obs: " + obs[:300]).strip())
    row["pressure_raw"] = (str(pa) if pa is not None else None)
    row["pressure_kind"] = ("exact" if pkpa is not None else None)
    prov(row, "o2", str(a.get("O2 % by volume") or ""))
    prov(row, "flow_cm_s", air, kind_only=True)
    add(**row)

# ---------- FLEX family (droplets) ----------
for i, r in enumerate(read("PSI-69_Experimental table_FLEX.csv"), 1):
    o2 = first(r["O initial ambient composition; mole fraction"])
    co2 = first(r["CO initial ambient composition; mole fraction"]) or 0
    he = first(r["He initial ambient composition; mole fraction"]) or 0
    n2 = first(r["N initial ambient composition; mole fraction"]) or 0
    dil = "+".join(n for n, v in (("N2", n2), ("CO2", co2), ("He", he)) if v and v > 0)
    p = first(r["Ambient pressure; mmHg"])
    end = r["Test end"].strip()
    add(psi_id="PSI-69", acronym="FLEX", source_table="FLEX", row_in_source=i, test_id=r["FLEX Identifier"], date=r["Test Date"],
        level="test", fuel_state="liquid", fuel=r["Fuel"], geometry="droplet",
        o2_pct_min=o2 * 100 if o2 is not None else None, o2_pct_max=o2 * 100 if o2 is not None else None,
        pressure_kpa=round(p * 0.133322, 2) if p else None, diluent=dil, flow_cm_s=0, flow_dir="quiescent",
        outcome=end.lower() or None, burn_time_s=first(r["Burn time; s"]),
        extinction_diam_mm=first(r["Visible flame extinction diameter; mm"]), droplet_d0_mm=first(r["Droplet initial diameter; mm"]),
        notes=f"CO2 frac {co2}; He frac {he}; burning rate {r['Burning rate; mm']}")

for i, r in enumerate(read("PSI-68_Experimental table_Flex2.csv"), 1):
    lo, hi = rng(r["Oxygen Mole Fraction"])
    plo, phi = rng(r["Ambient Pressure (atm)"])
    flo, fhi = rng(r["Flow Velocity (cm/s)"])
    add(psi_id="PSI-68", acronym="FLEX-2", source_table="Flex2", row_in_source=i, test_id=r["Sample (Fuel Type)"],
        level="campaign summary", fuel_state="liquid", fuel=r["Sample (Fuel Type)"], geometry="droplet",
        o2_pct_min=lo * 100 if lo is not None else None, o2_pct_max=hi * 100 if hi is not None else None,
        pressure_kpa=round(phi * 101.325, 1) if phi else None, diluent=r["Ambient Gas Mixture"],
        flow_cm_s=fhi, flow_dir="forced (droplet drift/flow)",
        notes=f"pressure {plo}-{phi} atm; flow {flo}-{fhi} cm/s; d0 {r['Initial Droplet Diameter (mm)']} mm")

for i, r in enumerate(read("PSI-39_Experimental table_CFI.csv"), 1):
    o2 = first(r["Oxygen"])
    p = r["Pressure"]
    pk = first(p) * 101.325 if first(p) is not None and "atm" in p.lower() else first(p)
    he = first(r["Helium"]) or 0
    add(psi_id="PSI-39", acronym="CFI", source_table="CFI", row_in_source=i, test_id=r["Flex Number"], date=r["Test Date"],
        level="test", fuel_state="liquid", fuel=r["Fuel"], geometry="droplet",
        o2_pct_min=o2 * 100 if o2 is not None and o2 <= 1 else o2, o2_pct_max=o2 * 100 if o2 is not None and o2 <= 1 else o2,
        pressure_kpa=round(pk, 1) if pk else None, diluent="N2+He" if he > 0 else "N2", flow_cm_s=0, flow_dir="quiescent",
        notes=f"fiber-supported: {r['Fiber']}")

# ---------- ACME gaseous ----------
for fn, ftype in (("PSI-159_Experimental table_CFI-G_Normal Flames.csv", "normal"), ("PSI-159_Experimental table_CFI-G_Inverse Flames.csv", "inverse")):
    for i, r in enumerate(read(fn), 1):
        xo2 = first(r.get("XO2 before test") or r.get("XO2"))
        hot = (r.get("Hot ignition") or "").strip().lower()
        term = (r.get("Self-ext or flow term") or r.get("Self -ext or flow term") or "").strip()
        outcome = "no ignition" if hot == "no" else ("self-extinguished" if term == "SE" else ("flow terminated" if term == "FT" else "ignited"))
        add(psi_id="PSI-159", acronym="ACME CFI-G", source_table=f"CFI-G {ftype}", row_in_source=i, test_id=r["Test"],
            level="test", fuel_state="gas", fuel=r["Fuel"], geometry=f"spherical porous burner ({ftype} flame)",
            o2_pct_min=xo2 * 100 if xo2 is not None else None, o2_pct_max=xo2 * 100 if xo2 is not None else None,
            pressure_kpa=round(first(r["approx p (bar)"]) * 100, 1) if first(r["approx p (bar)"]) else None,
            diluent="N2", flow_cm_s=None, flow_dir="burner outflow", outcome=outcome, burn_time_s=first(r["burn time (sec)"]),
            notes=f"cool flame: {r.get('Cool flame?','')}; {r.get('Comments','')}".strip("; "))

for fn, ftype in (("PSI-10_Experimental table_Flame Design_Normal Flame.csv", "normal"), ("PSI-10_Experimental table_Flame Design_Inverse Flame.csv", "inverse")):
    for i, r in enumerate(read(fn), 1):
        xo2 = first(r.get("XO2 (init)") or r.get("XO2"))
        add(psi_id="PSI-10", acronym="ACME Flame Design", source_table=f"Flame Design {ftype}", row_in_source=i, test_id=r["Test"],
            level="test", fuel_state="gas", fuel=r.get("Fuel") or "C2H4", geometry=f"spherical porous burner ({ftype} flame)",
            o2_pct_min=xo2 * 100 if xo2 is not None else None, o2_pct_max=xo2 * 100 if xo2 is not None else None,
            pressure_kpa=round(first(r["pmean (atm)"]) * 101.325, 1) if first(r["pmean (atm)"]) else None,
            diluent="N2", flow_dir="burner outflow", notes=f"Tad {r.get('Tad (K)','')} K; Zst {r.get('mean Zst','')}")

for i, r in enumerate(read("PSI-107_Experimental table_Spice.csv"), 1):
    add(psi_id="PSI-107", acronym="SPICE", source_table="SPICE", row_in_source=i, test_id=f"GMT{r['GMT date']} {r['GMT ignition']}",
        level="test", fuel_state="gas", fuel=r["Fuel"], geometry=f"coflow jet, nozzle {r['Nozzle (mm)']} mm",
        o2_pct_min=21, o2_pct_max=21, flow_cm_s=first(r["Air Rate (cm/s)"]), flow_dir="coflow",
        notes=f"fuel rate {r['Fuel Rate (mg/s)']} mg/s; O2 assumed cabin air")

for i, r in enumerate(read("PSI-20_Experimental table_ACME BRE.csv"), 1):
    lo, hi = rng(r["Oxygen Conc (percent)"])
    add(psi_id="PSI-20", acronym="ACME BRE", source_table="ACME BRE", row_in_source=i, test_id=f"{r['Year']}-{r['Month']}-{r['Date']}",
        level="test-day summary", fuel_state="gas (solid emulator)", fuel=r["Fuel Bottle"], geometry=f"porous burner {r['Burner Size (mm)']} mm",
        o2_pct_min=lo, o2_pct_max=hi, diluent="N2", flow_cm_s=0, flow_dir="quiescent", n_flames=first(r["Flames Ignited"]),
        notes=r["Notes"][:200])

for i, r in enumerate(read("PSI-21_Experimental table_CLD Flame.csv"), 1):
    add(psi_id="PSI-21", acronym="ACME CLD Flame", source_table="CLD Flame", row_in_source=i, test_id=r["Test Day"],
        level="test-day summary", fuel_state="gas", fuel=r["Fuel Bottle"], geometry="coflow laminar diffusion flame",
        o2_pct_min=21, o2_pct_max=21, flow_dir="coflow", n_flames=first(r["Flames ignited"]),
        notes=f"fuel conc {r['Fuel conc. Range']}; {r['Test Type']}")

for i, r in enumerate(read("PSI-22_Experimental table_ACME E-FIELD Flames.csv"), 1):
    add(psi_id="PSI-22", acronym="ACME E-FIELD Flames", source_table="E-FIELD", row_in_source=i, test_id=r["Test Day"],
        level="test-day summary", fuel_state="gas", fuel=r["Fuel Bottle"], geometry="coflow burner + electric field",
        o2_pct_min=21, o2_pct_max=21, gravity="microgravity + E-field (buoyancy proxy)", n_flames=first(r["Flames Ignited"]),
        notes=f"mesh polarity {r['Mesh Polarity']}; fuel conc {r['Fuel Conc']}; {r['Test Type']}")

for i, r in enumerate(read("PSI-23_Experimental table_ACME s-Flame.csv"), 1):
    lo, hi = rng(r["Atmosphere*"])
    add(psi_id="PSI-23", acronym="ACME s-Flame", source_table="s-Flame", row_in_source=i, test_id=r["Test Day*"],
        level="test-day summary", fuel_state="gas", fuel=r["Fuel Bottle"], geometry="spherical porous burner",
        o2_pct_min=lo if lo and lo > 5 else None, o2_pct_max=hi if hi and hi > 5 else None, n_flames=first(r["Flames Ignited*"]),
        notes=f"atmosphere {r['Atmosphere*']}; {r['Test Type']}")

for i, r in enumerate(read("PSI-106_Experimental table_Slice.csv"), 1):
    add(psi_id="PSI-106", acronym="SLICE", source_table="SLICE", row_in_source=i, test_id=r["Test Date"][:11],
        level="test-day summary", fuel_state="gas", fuel=r["Fuel Type"][:120], geometry="coflow jet", flow_dir="coflow",
        o2_pct_min=21, o2_pct_max=21, notes="O2 assumed cabin air")

# ---------- Detection ----------
for i, r in enumerate(read("PSI-101_Experimental table_SAME-R.csv"), 1):
    add(psi_id="PSI-101", acronym="SAME-R", source_table="SAME-R", row_in_source=i, test_id=r["SAME Test #"], date=r["Date"],
        level="test", fuel_state="solid (smoke source)", fuel=r["Sample Type"], geometry="heated sample (smoke generation)",
        flow_cm_s=first(r["Inlet velocity (cm/s)"]), flow_dir="duct", o2_pct_min=21, o2_pct_max=21,
        notes=f"{r['Description']}; Rt/R0 {r['Rt/R0']}; duration {r['Duration (sec)']} s; net aging {r['Net aging time (sec)']} s")

for i, r in enumerate(read("PSI-102_Experimental table_SAME.csv"), 1):
    add(psi_id="PSI-102", acronym="SAME", source_table="SAME", row_in_source=i, test_id=r["Sample #"],
        level="test", fuel_state="solid (smoke source)", fuel=r["Sample Material"], geometry="heated sample (smoke generation)",
        flow_cm_s=first(r["Air Flow (cm/s)"]), flow_dir="duct", o2_pct_min=21, o2_pct_max=21,
        notes=f"weight loss {r['Weight loss rate (mg/min)']} mg/min; aging {r['Aging Duration (minutes)']} min")

for i, r in enumerate(read("PSI-47_Experimental table_DAFT.csv"), 1):
    add(psi_id="PSI-47", acronym="DAFT / DAFT-2", source_table="DAFT", row_in_source=i, test_id=r["Session Name"],
        level="session", fuel_state="n/a (dust aerosol)", fuel=r["Sample Material"][:80], geometry="ambient sampling",
        notes=f"{r['Hardware Description']}; {r['Sampled Location']}")

for i, r in enumerate(read("PSI-142_Experimental table_Data Summary Table.csv"), 1):
    add(psi_id="PSI-142", acronym="PSI-142 (cool flame extinction, ground)", source_table="Data Summary", row_in_source=i,
        test_id=r["Data ID"], level="dataset", fuel_state="liquid/gas", gravity="ground study (uses FLEX)",
        notes=f"{r['Data Description']}; ref {r['Reference Publication Link']} fig {r['Figure ID in Reference']}")

# data-quality pass: every correction is logged in notes and qa_flag.
#
# Two rules govern this pass (commits 4, 5, 7):
#   1. The original value is never destroyed. A value excluded from an analysis is
#      preserved in a *_raw field so it can be recovered from the exported data.
#   2. A quality flag marks one variable, not the whole row. `qa_flag` keeps the
#      legacy single-flag column, and `flow_valid` / `o2_final_valid` give the
#      per-variable validity the app needs to avoid dropping a whole observation
#      because one of its columns is suspect.
for t in tests:
    t["qa_flag"] = ""
    if t["thickness_mm"] == 0:
        t["thickness_mm"] = None

    # Keep the signed originals before any magnitude or validity decision.
    if t.get("flow_cm_s_raw") in (None, ""):
        t["flow_cm_s_raw"] = t["flow_cm_s"]
    if t.get("flow_cm_s_min_raw") in (None, ""):
        t["flow_cm_s_min_raw"] = t["flow_cm_s_min"]
    t["flow_valid"] = 1

    for k in ("o2_pct_min", "o2_pct_max"):
        v = t[k]
        if v is not None and v > 100:
            c = v / 100
            if 10 <= c <= 100:
                t[k] = c
                t["qa_flag"] = "o2_corrected"
                t["notes"] = (t["notes"] or "") + f" | QA: source O2 '{v:g}%' read as {c:g}% (typo); original preserved in o2_raw"
            else:
                t[k] = None
                t["qa_flag"] = "o2_invalid"
                t["notes"] = (t["notes"] or "") + f" | QA: source O2 value {v:g} outside 0-100 %, excluded from analysis; original preserved in o2_raw"

    # A negative scalar flow is not a valid speed for an analysis that needs a
    # magnitude, but it is real source data and may encode direction. It is
    # flagged, not deleted: the signed value stays in flow_cm_s_raw and the
    # convention is documented in the README rather than inferred from the sign.
    fl = t["flow_cm_s"]
    if fl is not None and fl < 0:
        t["notes"] = (t["notes"] or "") + (
            f" | QA: negative scalar flow {fl:g} cm/s excluded from magnitude analyses; "
            f"signed value preserved in flow_cm_s_raw (sign convention not inferred)")
        t["flow_cm_s"] = None
        t["flow_valid"] = 0
        t["qa_flag"] = "flow_invalid"
    flm = t["flow_cm_s_min"]
    if flm is not None and flm < 0:
        # BASS rows 3, 7, 8 and 10 have a negative minimum flow. The magnitude is
        # what the charts compare, so magnitude is used there and the signed
        # original is kept here.
        t["notes"] = (t["notes"] or "") + (
            f" | QA: negative minimum flow {flm:g} cm/s preserved in flow_cm_s_min_raw; "
            f"charts use its magnitude")

    if "ANOMALY" in (t["notes"] or "") and not t["qa_flag"]:
        t["qa_flag"] = "source_anomaly"

    # Pressure provenance recorded at source level; build_data.py applies the
    # cabin-pressure assumption and resolves the final measured/assumed/no_data state.
    if not t.get("pressure_source"):
        t["pressure_source"] = "measured" if t["pressure_kpa"] is not None else ""

with open(os.path.join(OUT, "tests.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(tests)
json.dump(tests, open(os.path.join(OUT, "tests.json"), "w"), indent=1, ensure_ascii=False)
print("tests rows:", len(tests))
