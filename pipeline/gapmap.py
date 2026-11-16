"""Gap map figures from clean/tests.csv. Usage: python3 -I gapmap.py <psi_dir>"""
import csv, os, sys, random
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = sys.argv[1]
R = list(csv.DictReader(open(os.path.join(BASE, "clean", "tests.csv"), encoding="utf-8")))
FIG = os.path.join(BASE, "figures"); os.makedirs(FIG, exist_ok=True)

def f(x):
    try: return float(x)
    except: return None

def state(r):
    s = r["fuel_state"]
    if s.startswith("solid (smoke"): return None
    if s.startswith("solid"): return "Solid materials"
    if s.startswith("liquid"): return "Liquid droplets"
    if s.startswith("gas"): return "Gaseous flames"
    return None

INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
COL = {"Solid materials": "#2a78d6", "Liquid droplets": "#eb6834", "Gaseous flames": "#1baf7a"}
LUNAR = (30, 34)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF})

fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1.05, 1]})
random.seed(1)
order = ["Solid materials", "Liquid droplets", "Gaseous flames"]
for yi, s in enumerate(order):
    xs = [f(r["o2_pct_max"]) for r in R if r["level"] in ("test", "test-day summary") and state(r) == s and f(r["o2_pct_max"]) is not None]
    ys = [yi + random.uniform(-0.28, 0.28) for _ in xs]
    a.scatter(xs, ys, s=16, color=COL[s], alpha=0.55, edgecolor=SURF, linewidth=0.6, zorder=3)
    hi = sum(1 for x in xs if x >= LUNAR[0])
    a.text(107, yi, f"{len(xs)} rows\n{hi} at ≥30% O₂", va="center", ha="right", fontsize=9, color=INK)
a.axvspan(*LUNAR, color="#d9d7d0", alpha=0.6, zorder=1)
a.axvline(21, color=INK2, lw=1, ls=(0, (3, 3)), zorder=2)
a.text(21.4, 2.62, "Earth air 21%", fontsize=8.5, color=INK2)
a.text(32, -0.62, "Lunar habitat\ntarget 30–34%", fontsize=8.5, color=INK, ha="center", va="bottom")
a.set_yticks(range(3)); a.set_yticklabels(order, color=INK)
a.set_xlim(10, 108); a.set_ylim(-0.7, 2.8); a.set_xlabel("Oxygen concentration (% by volume)")
a.grid(axis="x", color=GRID, lw=0.8); a.set_axisbelow(True)
for sp in ("top", "right", "left"): a.spines[sp].set_visible(False)
a.set_title("No solid-material test in PSI reaches 23% O₂", loc="left", fontsize=12.5, color=INK, fontweight="bold")

sol = [r for r in R if state(r) == "Solid materials" and f(r["o2_pct_max"]) is not None and f(r["flow_cm_s"]) is not None]
grp = {"BASS": ("#2a78d6", "o"), "BASS-II": ("#eb6834", "s"), "SAFFIRE-I": ("#1baf7a", "D"), "SAFFIRE-II": ("#1baf7a", "D"), "SAFFIRE-III": ("#1baf7a", "D")}
done = set()
for r in sol:
    c, m = grp.get(r["acronym"], ("#888", "o"))
    lab = "SAFFIRE (large scale)" if r["acronym"].startswith("SAFFIRE") else r["acronym"]
    b.scatter(f(r["flow_cm_s"]), f(r["o2_pct_max"]), s=22, color=c, marker=m, alpha=0.7, edgecolor=SURF, linewidth=0.6,
              label=None if lab in done else lab, zorder=3)
    done.add(lab)
b.axhspan(*LUNAR, color="#d9d7d0", alpha=0.6, zorder=1)
b.axhline(21, color=INK2, lw=1, ls=(0, (3, 3)), zorder=2)
b.text(44, 32, "Lunar target: 0 solid tests", ha="right", va="center", fontsize=9, color=INK, fontweight="bold")
b.set_xlim(-1, 46); b.set_ylim(12, 36)
b.set_xlabel("Forced air flow (cm/s)"); b.set_ylabel("Oxygen (% by volume)")
b.grid(color=GRID, lw=0.8); b.set_axisbelow(True)
for sp in ("top", "right"): b.spines[sp].set_visible(False)
b.legend(frameon=False, loc="lower right", fontsize=9)
b.set_title(f"Solid-material tests by flow and O₂ (n={len(sol)})", loc="left", fontsize=12.5, color=INK, fontweight="bold")
fig.text(0.01, 0.01, "Source: NASA PSI experimental tables + BASS as-run matrix, normalized (Flame in Freefall dataset, 14-Nov-2026). Microgravity, ~1 atm.",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(os.path.join(FIG, "gap_map_o2.png"), dpi=170)
print("saved", os.path.join(FIG, "gap_map_o2.png"), len(sol))
