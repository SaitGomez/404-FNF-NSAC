"""Build investigation-level table: PSI metadata + expert tags + stats derived from tests.
Usage: python3 -I investigations.py <psi_dir>
"""
import json, csv, glob, os, sys, re, html

BASE = sys.argv[1]
OUT = os.path.join(BASE, "clean")

# Expert tags (team judgement; edit freely). relevance 0-3: iss, spacecraft, lunar_base, rover, mars
TAGS = {
 "PSI-25":  dict(priority="A", pillar="Prevention", fuel_state="solid", rel=(3,3,3,3,3), earth="Building/vehicle material flammability; wildfire spread models"),
 "PSI-26":  dict(priority="A", pillar="Prevention", fuel_state="solid", rel=(3,3,3,3,3), earth="Material flammability testing"),
 "PSI-98":  dict(priority="A", pillar="Prevention", fuel_state="solid", rel=(3,3,3,3,3), earth="Large-scale fire growth in confined spaces"),
 "PSI-99":  dict(priority="A", pillar="Prevention", fuel_state="solid", rel=(3,3,3,3,3), earth="Validates 1-g material screening tests"),
 "PSI-100": dict(priority="A", pillar="Prevention", fuel_state="solid", rel=(3,3,3,3,3), earth="Large-scale fire growth in confined spaces"),
 "PSI-102": dict(priority="A", pillar="Detection",  fuel_state="solid (smoke)", rel=(3,3,3,3,3), earth="Smoke detectors that tell smoke from dust (mining, industry)"),
 "PSI-101": dict(priority="A", pillar="Detection",  fuel_state="solid (smoke)", rel=(3,3,3,3,3), earth="Smoke detectors that tell smoke from dust (mining, industry)"),
 "PSI-69":  dict(priority="A", pillar="Suppression", fuel_state="liquid", rel=(3,3,2,2,2), earth="Fine-water-mist and inert-gas suppression; fuel spray combustion"),
 "PSI-68":  dict(priority="A", pillar="Suppression", fuel_state="liquid", rel=(3,3,2,2,2), earth="Fuel droplet burning; suppression"),
 "PSI-159": dict(priority="A", pillar="Prevention (high O2)", fuel_state="gas", rel=(2,2,3,3,2), earth="Oxygen-enriched environments (hospitals, industry)"),
 "PSI-22":  dict(priority="A", pillar="Fundamental (partial-g proxy)", fuel_state="gas", rel=(1,1,3,2,3), earth="Electric-field flame control"),
 "PSI-20":  dict(priority="A", pillar="Prevention", fuel_state="gas (solid emulator)", rel=(3,3,3,3,3), earth="Material burning-rate screening"),
 "PSI-107": dict(priority="B", pillar="Detection (soot/smoke)", fuel_state="gas", rel=(2,2,2,2,2), earth="Soot emissions"),
 "PSI-106": dict(priority="B", pillar="Fundamental", fuel_state="gas", rel=(1,1,1,1,1), earth="Burner stability"),
 "PSI-47":  dict(priority="B", pillar="Detection (dust vs smoke)", fuel_state="n/a", rel=(3,2,3,3,3), earth="Dust monitoring; lunar/Mars dust nuisance alarms"),
 "PSI-39":  dict(priority="B", pillar="Fundamental (cool flames)", fuel_state="liquid", rel=(1,1,1,1,1), earth="Engine knock / low-temperature chemistry"),
 "PSI-62":  dict(priority="B", pillar="Prevention (modeling)", fuel_state="solid", rel=(2,2,2,2,2), earth="Flame-spread modeling"),
 "PSI-142": dict(priority="B", pillar="Fundamental (cool flames)", fuel_state="liquid", rel=(1,1,1,1,1), earth="Low-temperature chemistry"),
 "PSI-115": dict(priority="B", pillar="Detection (modeling)", fuel_state="solid (smoke)", rel=(2,2,2,2,2), earth="Smoke transport modeling"),
 "PSI-10":  dict(priority="C", pillar="Fundamental (soot/efficiency)", fuel_state="gas", rel=(1,1,1,1,1), earth="Cleaner combustion"),
 "PSI-21":  dict(priority="C", pillar="Fundamental", fuel_state="gas", rel=(1,1,1,1,1), earth="Cleaner combustion"),
 "PSI-23":  dict(priority="C", pillar="Fundamental", fuel_state="gas", rel=(1,1,1,1,1), earth="Cleaner combustion"),
 "PSI-117": dict(priority="C", pillar="Fundamental (cool flames, CFD)", fuel_state="liquid", rel=(1,1,1,1,1), earth="Low-temperature chemistry"),
 "PSI-60":  dict(priority="C", pillar="Fundamental (soot, modeling)", fuel_state="gas", rel=(1,1,1,1,1), earth="Soot modeling"),
}

def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()

def f(x):
    try: return float(x)
    except: return None

tests = list(csv.DictReader(open(os.path.join(OUT, "tests.csv"), encoding="utf-8")))
rows, pubs = [], []
for p in sorted(glob.glob(os.path.join(BASE, "metadata", "PSI-*.json")), key=lambda x: int(re.findall(r"\d+", os.path.basename(x))[0])):
    d = json.load(open(p))
    pid = d["accession"]
    if pid not in TAGS:
        continue
    t = TAGS[pid]
    T = [r for r in tests if r["psi_id"] == pid]
    o2 = [v for r in T for v in (f(r["o2_pct_min"]), f(r["o2_pct_max"])) if v is not None]
    fl = [f(r["flow_cm_s"]) for r in T if f(r["flow_cm_s"]) is not None]
    pk = [f(r["pressure_kpa"]) for r in T if f(r["pressure_kpa"]) is not None]
    for pb in d.get("publications", []) or []:
        pubs.append(dict(psi_id=pid, acronym=d.get("investigationAcronym", ""), title=clean(pb.get("title")), authors=clean(pb.get("authorList")), doi=(pb.get("doi") or "").strip()))
    rows.append(dict(
        psi_id=pid, acronym=d.get("investigationAcronym") or "", title=clean(d.get("title")), doi=d.get("doi"),
        url=f"https://psi.nasa.gov/physci/repo/data/investigations/{pid}",
        priority=t["priority"], pillar=t["pillar"], fuel_state=t["fuel_state"],
        rel_iss=t["rel"][0], rel_spacecraft=t["rel"][1], rel_lunar_base=t["rel"][2], rel_rover=t["rel"][3], rel_mars=t["rel"][4],
        earth_applications=t["earth"], project_type=d.get("projectType"), platform=d.get("flightProgram"),
        hardware=clean(d.get("experimentHardware")), start=d.get("investigationStartDate"), end=d.get("investigationEndDate"),
        size_gb=round((d.get("totalFileSize") or 0) / 1e9, 1), n_publications=len(d.get("publications") or []),
        n_table_rows=len(T), o2_pct_min=min(o2) if o2 else None, o2_pct_max=max(o2) if o2 else None,
        flow_cm_s_min=min(fl) if fl else None, flow_cm_s_max=max(fl) if fl else None,
        pressure_kpa_min=min(pk) if pk else None, pressure_kpa_max=max(pk) if pk else None,
        objective=clean(d.get("objective")), approach=clean(d.get("approach")), hypothesis=clean(d.get("hypothesis")),
        research_impacts=clean(d.get("researchImpacts")), related=d.get("related_glds"), license=d.get("licenseIdentifier"),
    ))

fields = list(rows[0].keys())
with open(os.path.join(OUT, "investigations.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
json.dump(rows, open(os.path.join(OUT, "investigations.json"), "w"), indent=1, ensure_ascii=False)
with open(os.path.join(OUT, "publications.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["psi_id", "acronym", "title", "authors", "doi"]); w.writeheader(); w.writerows(pubs)
print("investigations", len(rows), "publications", len(pubs), "with DOI", sum(1 for p in pubs if p["doi"]))
for r in rows:
    print(f"{r['psi_id']:8s} {r['acronym'][:20]:20s} {r['priority']} rows={r['n_table_rows']:4d} O2={r['o2_pct_min']}-{r['o2_pct_max']} flow={r['flow_cm_s_min']}-{r['flow_cm_s_max']} P={r['pressure_kpa_min']}-{r['pressure_kpa_max']}")
