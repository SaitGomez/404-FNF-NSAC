"""Build the embedded data bundle for the FlameBench prototype.
Usage: python3 -I build_data.py <psi_dir> <out_json>

All user-facing strings produced here are English: the dashboard is an
English-language interface, so outcome labels, environment names, measurement
names and the curated investigation text are written in English and are not
translated at display time.

Provenance carried into the bundle (see pipeline/normalize.py for the source
side):
  ind      1 when the row is one individual experimental run (level == "test")
  plot     1 when the row may appear as an individual point. This says the
           record is an individual test, NOT that every one of its variables is
           valid; per-variable validity is `q*` below.
  pstate   "measured" | "assumed" | "no_data" for total pressure
  o2i/o2f  calibrated initial and final O2 kept apart, with o2fv validity
  flminr   signed minimum flow as the source recorded it (fla/flb are magnitudes)
  outr     raw outcome code, stable for matching; `out` is the display label
  qo2/qp/qfl/qout  per-variable validity, so one bad column does not void a row
"""
import csv, io, json, os, re, sys, glob, html, math, collections

BASE, OUT = sys.argv[1], sys.argv[2]

BUILT = "2026-11-15"      # bundle build date
CHECKED = "2026-11-15"    # date external/temporal claims were last checked


def f(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except Exception:
        return None


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def r2(v, n=2):
    return None if v is None else round(v, n)


def i0(x):
    """CSV integers that may arrive as '', '0', '1' or None."""
    try:
        return int(float(x))
    except Exception:
        return 0


# ---------------------------------------------------------------- curated investigation content
# pil: pillars (prev, det, sup, fund) · hw: hardware group · rel: relevance 0-3 for iss, nave, luna, rover, marte, traje
# meas: measurement tags · g1: has 1-g comparison data · parent: parent investigation for ground studies
C = {
 "PSI-25": dict(pil=["prev", "sup"], pri="A", hw="MSG + SPICE duct", rel=[3, 3, 3, 3, 3, 2], g1=True,
  sum="Burns solid samples (PMMA as sheets, rods and spheres; SIBAL fabric) inside a small wind tunnel in the Microgravity Science Glovebox. Varies air-flow speed and direction and lowers oxygen with nitrogen to find the limits of ignition, spread and extinction.",
  fuels="Clear and black PMMA (acrylic); SIBAL fabric (cotton and fibreglass)",
  samples="Sheets and films of 100 to 400 µm and of 1 to 5 mm; rods of 1/4\", 3/8\" and 1/2\"; spherical sections; fabrics 1 to 2 cm wide",
  varied="Flow speed (0 to 44 cm/s), flow direction (opposed or concurrent), O₂ (13.6 to 22.2 %), geometry and thickness",
  const="Cabin pressure (~1 atm), microgravity, same duct and igniter",
  meas=["video", "foto", "radiometro", "anemo", "gasO2", "gasCO2", "gasCO"],
  res=["U-shaped flammability boundary for PMMA rods: the minimum limiting O₂ is about 13.5 % at a stretch rate of 8 to 12 s⁻¹ (equation 6.1 of the report).",
       "The blow-off branch is linear in flow; extrapolating it to zero flow gives a conservative minimum O₂ for the material.",
       "At very low flow, quenching extinction appears, dominated by radiative heat loss. The 1-g upward limit (15.4 % O₂) falls inside the measured boundary once buoyancy is added."],
  src="BASS-II Summary Report, NASA/TM-20210011385 (PSI-25, Reports)", earth="Material selection for construction and transport; wildfire and building fire models"),
 "PSI-26": dict(pil=["prev", "sup"], pri="A", hw="MSG + SPICE duct", rel=[3, 3, 3, 3, 3, 2], g1=True,
  sum="First experiment of the BASS series. Burns real materials with opposed or concurrent air flow up to 40 cm/s and tests an inert gaseous suppressant (nitrogen) on several materials and geometries.",
  fuels="SIBAL fabric (75 % cotton, 25 % fibreglass), Nomex, Ultem, PMMA, paraffin candle",
  samples="Fabrics 1 to 2 cm wide; PMMA spheres of 1 and 2 cm; sheets; candle",
  varied="Flow speed and direction, material and geometry, cabin O₂ (15.9 to 22.7 %), N₂ discharge",
  const="Cabin pressure (0.97 to 1.01 atm), microgravity, Kanthal wire igniter",
  meas=["video", "foto", "radiometro", "anemo", "gasO2", "gasCO2"],
  res=["Relates the standard 1-g test (NASA-STD-6001 Test 1) to real flammability in microgravity using long in-flight burns.",
       "Includes wake flames, similar to a fire behind an object in a narrow space.",
       "Using nitrogen as a suppressant in microgravity links directly to current and planned extinguishing techniques."],
  src="PSI-26 metadata and As Run matrix (PSI-26, Science Documents)", earth="Material flammability testing"),
 "PSI-98": dict(pil=["prev"], pri="A", hw="Cygnus (Saffire)", rel=[3, 3, 3, 3, 3, 1], g1=True,
  sum="First large-scale fire in microgravity. Burns a 0.4 × 0.94 m SIBAL fabric sample with 20 cm/s of flow inside an uncrewed Cygnus cargo vehicle after it departed the ISS.",
  fuels="SIBAL fabric (cotton over fibreglass)", samples="One 0.4 × 0.94 m sample",
  varied="Flow direction (concurrent and opposed)", const="20 cm/s flow, cabin air (~21 % O₂), microgravity",
  meas=["video", "termopar", "radiometro", "presion", "gasO2", "gasCO2", "anemo"],
  res=["Measures how fast a large fire grows in low gravity, something impossible to test on a crewed vehicle.",
       "Provides O₂, CO₂, heat, pressure and flame-growth data to validate NASA's material selection criteria."],
  src="PSI-98 metadata", earth="Fire growth in enclosed spaces: mines, aircraft, submarines"),
 "PSI-99": dict(pil=["prev"], pri="A", hw="Cygnus (Saffire)", rel=[3, 3, 3, 3, 3, 1], g1=True,
  sum="Nine 5 × 29 cm samples of different materials, burned in a Cygnus with 20 or 30 cm/s of flow. The PSI table compares each microgravity result with the matching 1-g test.",
  fuels="Silicone (several thicknesses), SIBAL fabric, flat and structured PMMA, PMMA with Nomex", samples="Nine 5 × 29 cm samples",
  varied="Material, thickness, flow direction, speed (20 or 30 cm/s)", const="Cabin air (~21.5 to 22 % O₂), microgravity",
  meas=["video", "termopar", "radiometro", "presion", "gasO2", "gasCO2", "anemo"],
  res=["The four silicone samples did not sustain a flame in microgravity (~0 cm burned); in 1 g two of them burned completely.",
       "The SIBAL fabric burned completely (29 cm) both in microgravity and in 1 g.",
       "The PMMA burned about 10 cm in microgravity and burned completely in 1 g."],
  src="PSI-99 experimental table; sample identities cross-checked against the NASA Saffire II sample layout (NTRS 20150000894)",
  earth="Validating 1-g material tests"),
 "PSI-100": dict(pil=["prev"], pri="A", hw="Cygnus (Saffire)", rel=[3, 3, 3, 3, 3, 1], g1=True,
  sum="Repeats Saffire-I with the same SIBAL fabric but with 30 cm/s of flow instead of 20, in concurrent and opposed directions.",
  fuels="SIBAL fabric", samples="One large 0.4 × 0.94 m sample",
  varied="Flow direction", const="30 cm/s flow, cabin air, microgravity",
  meas=["video", "termopar", "radiometro", "presion", "gasO2", "gasCO2", "anemo"],
  res=["Allows comparison with Saffire-I of the effect of flow speed on a large fire.",
       "Records flow, flame and plume temperatures, radiation, pressure, CO₂ and O₂."],
  src="PSI-100 metadata", earth="Fire growth in enclosed spaces"),
 "PSI-102": dict(pil=["det"], pri="A", hw="MSG (SAME)", rel=[3, 3, 3, 3, 3, 1], g1=True,
  sum="Measures the size of the smoke particles that spacecraft materials produce when overheated in microgravity, and tests the Shuttle (ionisation) and ISS (photoelectric) smoke detectors against that smoke.",
  fuels="Teflon, Kapton, cellulose (lamp wick), silicone rubber, dibutyl phthalate", samples="Small samples heated by a wire for 15 to 60 s",
  varied="Material, air flow, heating temperature, smoke ageing time", const="Cabin air, microgravity",
  meas=["video", "tem", "partcount", "detIon", "detFoto", "masa"],
  res=["Smoke ages (particles grow) on time scales that matter for detection.",
       "The ISS light-scattering detector responds less to the smallest particles; the Shuttle ionisation detector responds somewhat better to them.",
       "No single detector works for every kind of smoke."],
  src="SAME Final Science Report (PSI-102) and NASA summary of SAME results (2022)", earth="Detectors for submarines, undersea laboratories and mining"),
 "PSI-101": dict(pil=["det"], pri="A", hw="MSG (SAME)", rel=[3, 3, 3, 3, 3, 1], g1=True,
  sum="Second SAME flight, with 66 test points in 2010. Adds the flame-retardant foam Pyrell, higher heating temperatures and cases with no flow during heating.",
  fuels="Teflon, Kapton, cellulose, silicone rubber, Pyrell (flame-retardant foam)", samples="Small heated samples",
  varied="Material, inlet velocity (flow), temperature, ageing time", const="Cabin air, microgravity",
  meas=["tem", "partcount", "detIon", "detFoto", "masa"],
  res=["Gives the microgravity smoke baseline against which to evaluate future detectors.",
       "Later ground tests allow the same smoke to be compared in 1 g."],
  src="SAME-R Final Report (PSI-101)", earth="Detectors for extreme environments"),
 "PSI-47": dict(pil=["det"], pri="B", hw="P-Trak instrument", rel=[3, 2, 3, 3, 3, 0], g1=False,
  sum="Feasibility test for SAME. Confirms that a commercial particle counter (P-Trak), modified to recirculate its alcohol by capillary action, measures correctly in microgravity using test dust.",
  fuels="No combustion: Arizona Red Dust aerosol", samples="Dust dispersed with N₂ in 15-litre Mylar bags",
  varied="Session and sampling location", const="Cabin air, microgravity",
  meas=["partcount", "masa"],
  res=["The modified P-Trak counted particles correctly in microgravity, compared against the DustTrak.",
       "The same instrument that measures smoke in SAME measures dust here: a basis for telling smoke from dust."],
  src="PSI-47 metadata", earth="Dust monitoring; false alarms from lunar or Martian dust"),
 "PSI-69": dict(pil=["sup"], pri="A", hw="MDCA in CIR", rel=[3, 3, 2, 2, 2, 1], g1=True,
  sum="Burns individual liquid fuel droplets and measures when they go out. Dilutes the chamber atmosphere with CO₂, helium or SF₆ to measure the effectiveness of each suppressant and the limiting oxygen index as a function of pressure.",
  fuels="Methanol and n-heptane", samples="Droplets of roughly 1.5 to 5 mm, free or fibre-supported",
  varied="O₂ (12 to 34 %), pressure (about 0.5 to 3 atm), diluent (N₂, CO₂, He), initial droplet diameter", const="Quiescent atmosphere, microgravity",
  meas=["video", "radiometro", "holl", "presion"],
  res=["Builds maps of the limiting oxygen index as a function of pressure and suppressant.",
       "Measures burning rate, extinction diameter, radiation and soot for each droplet.",
       "Observed cool flames: the droplet keeps reacting at low temperature after the visible flame goes out."],
  src="PSI-69 metadata and experimental table", earth="Suppression with inert gases and water mist; submarines and aircraft"),
 "PSI-68": dict(pil=["sup"], pri="A", hw="MDCA in CIR", rel=[2, 2, 2, 2, 2, 1], g1=False,
  sum="Continuation of FLEX with two-component fuels and surrogates for real fuels. Varies pressure from 0.5 to 3 atm and O₂ from 0.1 to 0.4 mole fraction.",
  fuels="Binary mixtures and pure fuels (see table)", samples="Fibre-supported or free droplets",
  varied="Fuel, O₂, pressure, diluent, imposed flow velocity", const="Microgravity",
  meas=["video", "radiometro", "holl", "presion"],
  res=["Reference data for validating two-component droplet simulations.",
       "Studies flame extinction and the effect of a slow flow over the droplet."],
  src="PSI-68 metadata", earth="Cleaner combustion of liquid fuels"),
 "PSI-39": dict(pil=["fund"], pri="B", hw="MDCA in CIR", rel=[1, 1, 1, 1, 1, 0], g1=False,
  sum="Studies cool flames in n-dodecane droplets and its mixtures, at pressures of 0.25 to 5 atm and with helium dilution.",
  fuels="n-dodecane, n-dodecane/iso-dodecane mixtures, farnesane", samples="Droplets suspended between needles or held on silicon carbide fibres",
  varied="Pressure, O₂, He dilution, droplet size, fuel", const="Quiescent atmosphere, microgravity",
  meas=["video", "radiometro"],
  res=["Relates droplet size, pressure and cool-flame extinction.",
       "Provides validation for low-temperature chemical kinetics mechanisms."],
  src="PSI-39 metadata", earth="Efficient engine design; low-temperature chemistry"),
 "PSI-159": dict(pil=["prev", "fund"], pri="A", hw="ACME in CIR", rel=[2, 2, 3, 3, 2, 3], g1=False,
  sum="Spherical diffusion flames with propane, n-butane and n-pentane, normal and inverse. In the inverse flames the oxidiser leaves the burner with up to 85 % O₂: these are the highest-oxygen microgravity tests in PSI.",
  fuels="Diluted propane, n-butane and n-pentane", samples="Spherical porous burner",
  varied="O₂ (up to 85 %), pressure (0.5 to 3.3 bar), fuel and dilution, flow rate, flame type (normal or inverse)", const="Microgravity, same ACME burner",
  meas=["video", "radiometro", "pmt", "termopar"],
  res=["Determines the conditions under which cool diffusion flames appear.",
       "Records for each test whether hot ignition occurred, whether the flame self-extinguished and how long it lasted."],
  src="PSI-159 metadata and experimental tables", earth="Oxygen-enriched environments; ultra-lean combustion engines"),
 "PSI-20": dict(pil=["prev"], pri="A", hw="ACME in CIR", rel=[3, 3, 3, 3, 3, 2], g1=False,
  sum="Uses gas to emulate the burning of solid and liquid materials over 25 and 50 mm porous burners in a quiescent atmosphere. Examines the atmospheres NASA is considering for crewed missions: 14.7 psia with 21 % O₂, 10.2 psia with 26.5 % and 8.2 psia with 34 %.",
  fuels="Methane and ethylene diluted with N₂ (emulating PMMA, nylon and other materials)", samples="Circular porous burners of 25 and 50 mm",
  varied="O₂, pressure, fuel, flow rate, burner size", const="No-flow atmosphere, microgravity",
  meas=["video", "radiometro", "termopar", "hflux"],
  res=["In atmospheres with elevated O₂ the flame kept burning almost steadily with no air flow.",
       "With 21 % O₂ those flames self-extinguished within a short time.",
       "Preliminary result: cutting ventilation may not be enough in exploration atmospheres; suggests greater use of the cone calorimeter test (Test 2)."],
  src="PSI-20 metadata (Research Impacts)", earth="Classifying materials by burning rate"),
 "PSI-22": dict(pil=["fund"], pri="A", hw="ACME in CIR", rel=[1, 1, 3, 2, 3, 0], g1=False, proxy=True,
  sum="Applies an electric field of up to 10 kV between the burner and a mesh. The field drags the flame's ions and creates an ionic wind that imitates the effect of buoyancy, that is, an artificial partial gravity.",
  fuels="Methane and ethylene diluted with N₂", samples="Jet burner and coflow burner",
  varied="Field voltage and polarity, fuel, dilution, with and without coflow", const="Microgravity",
  meas=["video", "ion"],
  res=["Measures the ion current through the flame and its response time to the field.",
       "It is the only approach to partial gravity within PSI."],
  src="PSI-22 metadata and challenge statement", earth="Flame control with electric fields"),
 "PSI-107": dict(pil=["det", "fund"], pri="B", hw="MSG + SPICE duct", rel=[2, 2, 2, 2, 2, 0], g1=True,
  sum="Determines the smoke point (when a flame starts to release soot) of jet flames with air coflow in microgravity. Studied 526 flames.",
  fuels="Methane, ethylene, propane, propylene and mixtures", samples="Nozzles of 0.41, 0.76 and 1.6 mm",
  varied="Fuel, nozzle diameter, fuel flow rate, coflow velocity (5.4 to 65 cm/s)", const="Cabin air, microgravity",
  meas=["video", "foto", "radiometro", "anemo"],
  res=["Relates the luminous flame length to the smoke point.",
       "Quantifies the sooting tendency of each fuel."],
  src="PSI-107 metadata", earth="Soot emissions"),
 "PSI-106": dict(pil=["fund"], pri="B", hw="MSG + SPICE duct", rel=[1, 1, 1, 1, 1, 0], g1=True,
  sum="Studies the structure and stability of laminar diffusion flames: when they lift off the burner depending on fuel, dilution and coflow.",
  fuels="Methane, ethylene and mixtures diluted with N₂", samples="Interchangeable burner tubes",
  varied="Fuel, dilution, burner diameter, coflow velocity", const="Cabin air, microgravity",
  meas=["foto", "anemo", "termopar", "holl"],
  res=["Lift-off velocity limits for several fuels and diameters.", "More than 4,000 high-resolution images across 13 experiments."],
  src="PSI-106 metadata", earth="Burner stability"),
 "PSI-10": dict(pil=["fund"], pri="C", hw="ACME in CIR", rel=[1, 1, 1, 1, 1, 1], g1=False,
  sum="Spherical diffusion flames of ethylene and methane, normal and inverse, to find the limits of soot inception.",
  fuels="Ethylene and methane", samples="Spherical porous burner",
  varied="O₂, pressure, flow rate, stoichiometric mixture fraction, inert (N₂ or CO₂)", const="Microgravity",
  meas=["video", "radiometro", "pmt", "termopar"],
  res=["Soot inception limits as a function of flow rate, dilution and pressure.", "Flame temperature, size and colour per test."],
  src="PSI-10 metadata", earth="Combustion with fewer pollutants"),
 "PSI-21": dict(pil=["fund"], pri="C", hw="ACME in CIR", rel=[1, 1, 1, 1, 1, 0], g1=False,
  sum="Coflow diffusion flames of methane and ethylene, from heavily diluted (near extinction) to heavily sooting, to test computational models.",
  fuels="Diluted methane and ethylene", samples="Coflow burner",
  varied="Fuel dilution, velocity", const="Microgravity",
  meas=["video", "pmt", "holl", "termopar"],
  res=["Flame shape, lift-off height and extinction limits.", "Sooting tendency at long residence times."],
  src="PSI-21 metadata", earth="Soot models"),
 "PSI-23": dict(pil=["fund"], pri="C", hw="ACME in CIR", rel=[1, 1, 1, 1, 1, 0], g1=False,
  sum="Spherical flames with hydrogen, methane and ethylene to measure their transient structure and extinction limits.",
  fuels="Hydrogen, methane and ethylene with diluents", samples="Spherical porous burner",
  varied="Fuel and diluent mixture, flow rate, atmosphere", const="Microgravity",
  meas=["video", "termopar", "radiometro", "presion"],
  res=["Kinetic and radiative extinction limits of spherical flames.", "Data for comparison with detailed simulations."],
  src="PSI-23 metadata", earth="Engine efficiency"),
 "PSI-62": dict(pil=["prev"], pri="B", hw="Ground study", rel=[2, 2, 2, 2, 2, 0], g1=False, parent="PSI-25",
  sum="Ground study using the BASS and BASS-II data. Develops and validates a modelling method (flamelet generated manifolds) for concurrent flame spread in microgravity.",
  fuels="PMMA (sheets, spheres, rods) and wax cylinders, taken from BASS", samples="BASS and BASS-II geometries",
  varied="Simulated geometry and material", const="Microgravity",
  meas=["cfd"],
  res=["Predictive tools for estimating the flammability limits of new materials.", "3D reconstructions of soot and temperature from the BASS imagery."],
  src="PSI-62 metadata", earth="Flame spread modelling"),
 "PSI-115": dict(pil=["det"], pri="B", hw="Ground study", rel=[2, 2, 2, 2, 2, 0], g1=True, parent="PSI-102",
  sum="Ground study with the SAME data. Uses numerical simulation to explain why pyrolysis smoke grows differently in microgravity and in Earth gravity.",
  fuels="Pyrolysis smoke (SAME data)", samples="Not applicable (simulation)",
  varied="Gravity (microgravity and 1 g)", const="—",
  meas=["cfd"],
  res=["Quantifies the differences between microgravity smoke and 1-g smoke.", "Identifies the flow mechanisms that cause those differences."],
  src="PSI-115 metadata", earth="Smoke transport models"),
 "PSI-117": dict(pil=["fund"], pri="C", hw="Ground study", rel=[1, 1, 1, 1, 1, 0], g1=False, parent="PSI-69",
  sum="Ground study with the FLEX data. An OpenFOAM CFD model of droplet cool flames, to see how thermal perturbations and droplet drag change ignition and extinction.",
  fuels="n-alkanes (FLEX data)", samples="Droplets of 0.5 to 4 mm (simulated)",
  varied="Convection, heating, ambient composition, pressure", const="Microgravity",
  meas=["cfd"],
  res=["Stability maps: onset, persistence and quenching of the cool flame.", "Explains the variability between FLEX tests."],
  src="PSI-117 metadata", earth="Low-temperature chemistry"),
 "PSI-142": dict(pil=["fund"], pri="B", hw="Ground study", rel=[1, 1, 1, 1, 1, 0], g1=False, parent="PSI-69",
  sum="Ground study with the FLEX data. Simulations and counterflow flame experiments to map the flammability limits of cool flames.",
  fuels="n-heptane, dimethyl ether", samples="Counterflow flames (laboratory)",
  varied="O₂, pressure, stretch", const="1 g (laboratory) and simulation",
  meas=["cfd", "termopar"],
  res=["A new flammability-limit diagram for cool diffusion flames.", "Verifies phenomena observed in the FLEX experiments on the ISS."],
  src="PSI-142 metadata", earth="Low-temperature chemistry"),
 "PSI-60": dict(pil=["fund"], pri="C", hw="Ground study", rel=[1, 1, 1, 1, 1, 0], g1=True, parent="PSI-107",
  sum="Ground study with the SPICE data. Combines processing of more than 1,600 images with soot models to explain the difference in soot formation between 1 g and microgravity.",
  fuels="SPICE fuels", samples="Not applicable (image analysis and simulation)",
  varied="Gravity, burner configuration", const="—",
  meas=["cfd", "holl"],
  res=["Temperature and soot volume fraction fields derived from the SPICE imagery."],
  src="PSI-60 metadata", earth="Soot models"),
}
MEAS = {"video": "Video", "foto": "Photography", "radiometro": "Radiometer", "termopar": "Thermocouples", "gasO2": "O₂ sensor",
        "gasCO2": "CO₂ sensor", "gasCO": "CO sensor", "presion": "Pressure", "anemo": "Flow velocity",
        "pmt": "Photomultiplier / chemiluminescence", "partcount": "Particle counter", "tem": "Microscope sampling (TEM)",
        "detIon": "Ionisation smoke detector", "detFoto": "Photoelectric smoke detector", "masa": "Aerosol mass / mass loss",
        "ion": "Ion current", "holl": "Soot measurement", "hflux": "Heat flux", "cfd": "Numerical simulation"}
ORDER = ["PSI-25", "PSI-26", "PSI-98", "PSI-99", "PSI-100", "PSI-102", "PSI-101", "PSI-47", "PSI-69", "PSI-68", "PSI-159", "PSI-20", "PSI-22",
         "PSI-107", "PSI-106", "PSI-39", "PSI-62", "PSI-115", "PSI-142", "PSI-10", "PSI-21", "PSI-23", "PSI-117", "PSI-60"]
# Investigations run inside a pressurised cabin (MSG or Cygnus) whose table omits
# pressure. Cabin pressure is assumed for these and the row is marked `assumed`.
ASSUMED_P = {"PSI-25", "PSI-107", "PSI-106", "PSI-102", "PSI-101", "PSI-98", "PSI-99", "PSI-100", "PSI-21", "PSI-22"}
ASSUMED_P_KPA = 101.3

# ---------------------------------------------------------------- tests
T = list(csv.DictReader(open(os.path.join(BASE, "clean", "tests.csv"), encoding="utf-8")))
TF = ["inv", "tbl", "tid", "lvl", "st", "fuel", "geom", "thk", "o2a", "o2b", "p", "pas", "dil", "fla", "flb", "dir", "grav", "out", "ign", "ext",
      "bt", "K", "dext", "d0", "co2", "he", "blug", "bl1g", "qa", "note",
      # provenance and per-variable quality, appended so existing indices hold
      "ind", "plot", "pstate", "o2i", "o2f", "o2fv", "flminr", "flmaxr", "outr",
      "o2k", "pk", "flk", "matinh", "matsrc", "o2raw", "qo2", "qp", "qfl", "qout"]


def st_norm(s):
    if s.startswith("solid (smoke"): return "smoke"
    if s.startswith("solid"): return "solid"
    if "emulator" in s: return "gas-emulator"
    if s.startswith("liquid"): return "liquid"
    if s.startswith("gas"): return "gas"
    return "other"


# Raw outcome code -> English display label. `outr` keeps the raw code so the app
# matches on a stable key instead of on display text.
OUTMAP = {"burned": "burned", "extinguished": "extinguished",
          "flow reduced to extinction": "flow reduced to extinction", "no ignition": "no ignition",
          "no sustained burning": "no sustained burning", "self-extinguished": "self-extinguished",
          "flow terminated": "flow terminated by operator", "ignited": "ignited",
          "extinction": "droplet flame extinction", "disruption": "droplet disruption",
          "completion": "droplet burned to completion"}
# Outcome codes that mean the flame was put out, and those that mean it burned.
EXT_CODES = {"extinguished", "flow reduced to extinction", "self-extinguished", "extinction"}
BURN_CODES = {"burned", "completion", "flow terminated", "ignited"}
NOIGN_CODES = {"no ignition", "no sustained burning"}

tests = []
for r in T:
    pid = r["psi_id"]
    if pid not in C: continue
    o = (r["outcome"] or "").strip().lower()
    lvl = r["level"]
    ind = 1 if lvl == "test" else 0
    ign = None if not o else (0 if o in NOIGN_CODES else 1)
    ext = None if not o else (1 if o in EXT_CODES else (0 if o in BURN_CODES else None))
    note = r["notes"] or ""
    K = None; co2 = None; he = None
    if pid == "PSI-69":
        m = re.search(r"burning rate ([\d.]+)", note); K = float(m.group(1)) if m else None
        m = re.search(r"CO2 frac ([\d.]+)", note); co2 = float(m.group(1)) * 100 if m else 0
        m = re.search(r"He frac ([\d.]+)", note); he = float(m.group(1)) * 100 if m else 0

    # Pressure provenance (commit 7). Three states, derived from the source value
    # and the assumption rule, not from whether the numeric field ended up filled.
    p = f(r["pressure_kpa"]); pas = 0
    if p is not None:
        pstate = "measured"
    elif pid in ASSUMED_P and lvl in ("test", "test-day summary"):
        p = ASSUMED_P_KPA; pas = 1; pstate = "assumed"
    else:
        pstate = "no_data"

    bl = f(re.sub(r"[^\d.]", "", (r["burn_length_cm"] or "").split("cm")[0])) if pid == "PSI-99" and r["burn_length_cm"] else None
    b1 = r["burn_length_1g"] or ""
    bl1 = 29.0 if "Complete" in b1 else f(re.sub(r"[^\d.]", "", b1.split("cm")[0])) if b1.strip() else None
    grav = "ug"
    if "E-field" in r["gravity"]: grav = "proxy"
    if "ground" in r["gravity"]: grav = "1g"

    # Flow: fla/flb are magnitudes for charts that compare speed; the signed
    # source values are kept in flminr/flmaxr (commit 5).
    fl_min_src = f(r.get("flow_cm_s_min_raw")) if r.get("flow_cm_s_min_raw") not in (None, "") else f(r["flow_cm_s_min"])
    fl_max_src = f(r.get("flow_cm_s_raw")) if r.get("flow_cm_s_raw") not in (None, "") else f(r["flow_cm_s"])
    fla = abs(f(r["flow_cm_s_min"])) if f(r["flow_cm_s_min"]) is not None else None
    flb = abs(f(r["flow_cm_s"])) if f(r["flow_cm_s"]) is not None else None

    qa = r["qa_flag"] or ""
    # Per-variable validity (commit 8): a flag voids one variable, not the row.
    qo2 = 0 if qa == "o2_invalid" else 1
    qfl = 1 if i0(r.get("flow_valid") or 1) else 0
    qp = 1 if pstate != "no_data" else 0
    qout = 1 if (ind and o) else 0

    tests.append([ORDER.index(pid), r["source_table"], r["test_id"], lvl, st_norm(r["fuel_state"]),
                  (r["fuel"] or "")[:60], (r["geometry"] or "")[:44],
                  r2(f(r["thickness_mm"]), 3), r2(f(r["o2_pct_min"])), r2(f(r["o2_pct_max"])), r2(p, 1), pas,
                  (r["diluent"] or "")[:24], r2(fla, 1), r2(flb, 1), (r["flow_dir"] or "")[:28], grav,
                  OUTMAP.get(o, o), ign, ext,
                  r2(f(r["burn_time_s"]), 1), r2(K, 3), r2(f(r["extinction_diam_mm"])), r2(f(r["droplet_d0_mm"])),
                  r2(co2, 1), r2(he, 1), bl, bl1, qa, note[:220],
                  ind, ind, pstate,
                  r2(f(r.get("o2_initial_pct"))), r2(f(r.get("o2_final_pct"))), i0(r.get("o2_final_valid")),
                  r2(fl_min_src, 1), r2(fl_max_src, 1), o,
                  r.get("o2_kind") or "", r.get("pressure_kind") or "", r.get("flow_cm_s_kind") or "",
                  i0(r.get("material_inherited")), r.get("material_source_row") or "",
                  r.get("o2_raw") or "", qo2, qp, qfl, qout])

# ---------------------------------------------------------------- investigations
pubs = collections.defaultdict(list)
for r in csv.DictReader(open(os.path.join(BASE, "clean", "publications.csv"), encoding="utf-8")):
    pubs[r["psi_id"]].append([r["title"][:140], r["doi"]])
IND_I, PLOT_I = TF.index("ind"), TF.index("plot")
inv = []
for i, pid in enumerate(ORDER):
    d = json.load(open(os.path.join(BASE, "metadata", pid + ".json")))
    c = C[pid]
    rows = [t for t in tests if t[0] == i]
    ind_rows = [t for t in rows if t[IND_I] == 1]

    def rng(a, b=None, src=None):
        src = rows if src is None else src
        v = [t[a] for t in src if t[a] is not None] + ([t[b] for t in src if t[b] is not None] if b is not None else [])
        return [min(v), max(v)] if v else None

    fuels = collections.Counter(t[5] for t in ind_rows if t[5])
    inv.append(dict(id=pid, acr=d.get("investigationAcronym") or clean(d.get("title"))[:48], title=clean(d.get("title")), doi=d.get("doi"),
                    type="Flight" if d.get("projectType", "").startswith("Micro") else "Ground study", platform=d.get("flightProgram") or "",
                    hwtxt=clean(d.get("experimentHardware")), start=d.get("investigationStartDate"), end=d.get("investigationEndDate"),
                    gb=round((d.get("totalFileSize") or 0) / 1e9, 1), npub=len(d.get("publications") or []),
                    n=len(rows), nind=len(ind_rows),
                    st=sorted(set(t[4] for t in rows)) or ["—"],
                    o2=rng(8, 9, ind_rows), p=rng(10, None, ind_rows), fl=rng(13, 14, ind_rows),
                    topfuels=[k for k, _ in fuels.most_common(6)], obj=clean(d.get("objective"))[:900], pubs=pubs[pid][:8], **c))

# ---------------------------------------------------------------- raw tables
raw = []
for fn in sorted(glob.glob(os.path.join(BASE, "tables", "*.csv"))):
    name = os.path.basename(fn)
    pid = name.split("_")[0]
    if pid not in C: continue
    rows = [r for r in csv.reader(io.StringIO(open(fn, encoding="utf-8", errors="replace").read())) if any(c.strip() for c in r)]
    hdr = [re.sub(r"\s+", " ", h).strip() for h in rows[0]]
    body = [[re.sub(r"\s+", " ", c).strip()[:90] for c in (r + [""] * len(hdr))[:len(hdr)]] for r in rows[1:]]
    raw.append(dict(inv=ORDER.index(pid), name=name.replace(pid + "_Experimental table_", "").replace(".csv", ""), file=name, cols=hdr, rows=body))

# ---------------------------------------------------------------- environments (sources in ext)
ENV = [
 dict(id="earth", name="Earth (reference)", o2=21, p=101.3, g=1, src="Challenge statement: 21 % O₂ and 14.7 psi at sea level"),
 dict(id="iss", name="Space station (ISS)", o2=21, p=101.3, g=0, src="Sea-level atmosphere on the ISS: 14.7 psia and 21 % O₂ (NASA NTRS 20240003211)"),
 dict(id="vehicle", name="Spacecraft (nominal cabin)", o2=21, p=101.3, g=0, src="Cabin at 14.7 psia and 21 % O₂"),
 dict(id="eva_prep", name="Spacecraft in EVA preparation", o2=26.5, p=70.3, g=0, src="Shuttle EVA pre-breathe atmosphere: 10.2 psia and 26.5 % O₂"),
 dict(id="lunar", name="Lunar base", o2=34, p=56.5, g=0.165, src="NASA recommended exploration atmosphere: 8.2 psia (56.5 kPa) and 34 % O₂. The challenge specifies ≥30 % O₂ and ≤10.2 psi"),
 dict(id="rover", name="Pressurised rover (Moon)", o2=34, p=56.5, g=0.165, src="The challenge specifies the same atmosphere for the lunar base and pressurised rovers"),
 dict(id="mars", name="Mars habitat", o2=34, p=56.5, g=0.38, src="Team assumption: same exploration atmosphere; Mars gravity 0.38 g"),
 dict(id="suit", name="Spacesuit (EVA)", o2=100, p=29.6, g=0, src="Challenge statement: 100 % O₂ at 4.3 psi"),
]

# ---------------------------------------------------------------- external evidence (level 2)
# Every entry that makes a claim about time carries `status` and `checked`
# (commit 17): mission status, experiment status and results availability are
# stated separately, and no entry asserts that an experiment has run without a
# source that says so.
EXT = [
 dict(id="saffire46", pil=["prev", "det", "sup"], kind="Flight experiment (outside PSI)", title="Saffire-IV, V and VI: large-scale fire in exploration atmospheres",
  status="Experiments performed; results published", checked=CHECKED,
  text="Continuation of Saffire I to III with thick fuels, longer burns and exploration atmospheres (more O₂, lower pressure). They also demonstrated fire detection, combustion-product monitoring and post-fire air cleanup. Saffire IV and V flew in 2020 and 2021; Saffire VI in December 2023.",
  url="https://ntrs.nasa.gov/api/citations/20240007488/downloads/Saffire%20ICES%202024%20Saffire%20presentation072124small.pdf", src="NASA, Preliminary Results from the Saffire VI Experiment (ICES 2024)"),
 dict(id="luci", pil=["prev"], kind="Suborbital experiment (outside PSI)", title="LUCI: first extended burn in simulated lunar gravity",
  status="Experiment performed; results presented at ASGSR 2025", checked=CHECKED,
  text="On 4 February 2025 a New Shepard capsule spun at about 11 rpm to simulate lunar gravity, with an effective rotation radius of 1.22 m at the experiment. LUCI burned a cotton-fibreglass fabric and a 4 mm PMMA rod at the same time, in air at normal pressure, for over two and a half minutes. These are the first combustion tests longer than 25 s in simulated lunar gravity.",
  url="https://ntrs.nasa.gov/citations/20250010653", src="NASA NTRS 20250010653, Lunar Combustion Investigation"),
 dict(id="fm2", pil=["prev"], kind="Planned experiment (outside PSI)", title="FM²: flammability of materials on the lunar surface",
  status="Planned. NASA targets launch in late 2026 on CLPS lander mission CP-21. Not flown and no results as of " + CHECKED,
  checked=CHECKED,
  text="Would be the first combustion experiment on another planetary body: a robotic, self-contained combustion chamber delivered to the lunar surface. Its environmental control system can reproduce 21 % O₂ at 14.7 psia and 34 % O₂ at 8.2 psia, the atmospheres of immediate interest to the Human Landing System and the lunar rover. Four samples are planned: two SIBAL cotton-fibreglass fabrics burned in air and two acrylic rods burned in normoxic exploration atmospheres, one of each upward and downward. Modelling, supported by parabolic flights and ISS tests, suggests some materials burn at lower oxygen concentrations in lunar gravity than on Earth; SIBAL fabric has been found to burn only downward in air in lunar gravity, where in Earth gravity it extinguishes immediately after ignition. Note: some press reports tie FM² to a crewed Artemis landing; NASA's own description assigns it to the robotic CLPS CP-21 mission.",
  url="https://www.nasa.gov/glenn/glenn-expertise-space-exploration/physical-sciences-program/combustion-science/flammability-of-materials-on-the-moon-fm2/", src="NASA Glenn, FM²; NASA NTRS 20240015307"),
 dict(id="sofie", pil=["prev", "sup"], kind="Flight experiment (outside PSI)", title="SoFIE: solid ignition and extinction on the ISS",
  status="Operating on the ISS since the first GEL test on 13 January 2023. GEL, MIST and RTDFS have run; NCA and SMuRF are still to come. Results presented at conferences; papers planned. Checked " + CHECKED,
  checked=CHECKED,
  text="An insert in the Combustion Integrated Rack built to meet the requirements of five investigations (RTDFS, NCA, GEL, MIST and SMuRF). The CIR chamber allows testing at oxygen concentrations and pressures representative of current and planned exploration atmospheres, and an 85 % O₂ supply bottle has been used on orbit. The first GEL test burned a 4 cm acrylic sphere starting at 17.5 % O₂ in nitrogen with 20 cm/s of flow. NCA is to burn flat PMMA with opposed flow at oxygen levels from atmospheric up to 85 %, adjusting pressure near the normoxic curve; SMuRF is to correlate 1-g tests with ventilated microgravity to help select more fire-resistant materials.",
  url="https://www.nasa.gov/glenn/glenn-expertise-space-exploration/physical-sciences-program/combustion-science/solid-fuel-ignition-and-extinction-sofie/", src="NASA Glenn, SoFIE; NASA ISS Daily Summary Reports; NASA Task Book"),
 dict(id="flare", pil=["prev"], kind="Flight experiment (outside PSI)", title="FLARE: relating 1-g limits to microgravity limits",
  status="Ongoing international project", checked=CHECKED,
  text="An international team from JAXA, NASA and ESA. It seeks a method to estimate microgravity flammability limits from ground tests, and from that to propose a new standard test for selecting spacecraft materials that corrects the limitations of standards such as NASA-STD-6001B.",
  url="https://www.nasa.gov/glenn/glenn-expertise-space-exploration/physical-sciences-program/combustion-science/flammability-limits-at-reduced-g-experiment-flare/", src="NASA Glenn, FLARE"),
 dict(id="std6001", pil=["prev"], kind="Standard", title="NASA-STD-6001 Test 1: the 1-g material test",
  status="Standard in force", checked=CHECKED,
  text="An upward flame-propagation test that decides whether a material may be used in a cabin. It is pass or fail: the standard sample is 30 cm and fails if the flame travels more than 15 cm or if it drops burning material. It is valid only for the atmosphere it was run in. Some researchers consider it not conservative in low gravity.",
  url="https://ntrs.nasa.gov/api/citations/20150004099/downloads/20150004099.pdf", src="NASA, Applying Flammability Limit Probabilities to NASA STD-6001 Test 1 (ICES 2014)"),
 dict(id="expatm", pil=["prev"], kind="Design atmosphere", title="Exploration atmosphere: 8.2 psia and 34 % O₂",
  status="Design recommendation", checked=CHECKED,
  text="NASA's exploration atmospheres working group recommended in 2005 a cabin at 8.0 psia and 32 % O₂ for missions with many excursions, and in 2012 adjusted it to 8.2 psia (56.5 kPa) and 34 % O₂. The decision balances three risks: material flammability, hypoxia and decompression sickness.",
  url="https://ntrs.nasa.gov/api/citations/20150021491/downloads/20150021491.pdf", src="NASA, Evidence Report: Risk of Hypobaric Hypoxia from the Exploration Atmosphere"),
 dict(id="detectors", pil=["det"], kind="Equipment in service", title="Smoke detectors: ionisation on the Shuttle, photoelectric on the ISS",
  status="Equipment in service", checked=CHECKED,
  text="The Shuttle used ionisation detectors with a separator that rejects particles larger than 1 to 2 µm. The ISS uses near-infrared light-scattering detectors, which are more sensitive to large particles. In microgravity smoke does not rise to the ceiling, so detection depends on the ventilation flow. With real SAME smoke, the ISS detector picked up cellulose, silicone and Pyrell smoke well, but frequently failed on the small particles of Teflon and Kapton, materials common in electronics.",
  url="https://ntrs.nasa.gov/api/citations/20220009167/downloads/DRI%20Talk%20v2.pdf", src="NASA NTRS 20220009167; NIST, SAME results"),
 dict(id="fwm", pil=["sup"], kind="Equipment in service", title="Portable fine water mist extinguisher on the ISS",
  status="Equipment in service", checked=CHECKED,
  text="The CO₂ extinguishers in the US segment created an unbreathable environment, because the emergency filter respirator does not remove CO₂. NASA replaced them with nine fine water mist extinguishers; the last arrived in 2016. The mist extinguishes mainly by removing heat rather than by displacing oxygen, which is why qualifying it requires evaluating geometry, temperature and heat transfer. A version for Orion is under development.",
  url="https://ntrs.nasa.gov/citations/20130011664", src="NASA NTRS 20130011664; NASA Spinoff"),
 dict(id="lessons", pil=["prev", "sup"], kind="Historical lesson", title="Apollo 1, Mir and Apollo 13: oxygen as the common factor",
  status="Historical record", checked=CHECKED,
  text="In 1967 the Apollo 1 crew died in a pre-launch test when fire broke out in a cabin filled with oxygen. In 1997 an oxygen generator failed and caused a fire on the Mir station. On Apollo 13 an oxygen tank exploded on the way to the Moon.",
  url="https://sma.nasa.gov/sma-disciplines/accllp/apollo-1", src="NASA SMA; NASA History"),
 dict(id="spinoffs", pil=["det", "sup", "prev"], kind="Application on Earth", title="Space technology in fire safety on Earth",
  status="In use on Earth", checked=CHECKED,
  text="Firefighters' air tanks were improved in the 1970s with spacesuit technology. A smoke detector developed for the Shuttle tells smoke from dust and gives fewer false alarms, useful in mining. Firefighters' clothing was improved in the 1980s with suit technology. Fine water mist extinguishers have direct use on Earth.",
  url="https://spinoff.nasa.gov/node/9407", src="NASA Spinoff 9582, 9407, 9918"),
]
# level-2 measured points for solids (outside PSI tables)
EXT_TESTS = [
 dict(name="Saffire IV-1", mat="SIBAL fabric", o2=22.0, p=100.0, fl=20, g=0, dir="concurrent", ref="saffire46"),
 dict(name="Saffire V-2", mat="Cotton jersey", o2=26.2, p=70.7, fl=20, g=0, dir="concurrent", ref="saffire46"),
 dict(name="Saffire VI-2", mat="SIBAL fabric", o2=31.0, p=54.1, fl=20, g=0, dir="concurrent", ref="saffire46"),
 dict(name="Saffire VI-3", mat="Two-sided PMMA (1 cm)", o2=30.3, p=54.6, fl=20, g=0, dir="concurrent", ref="saffire46"),
 dict(name="Saffire VI-4", mat="One-sided PMMA (0.5 cm)", o2=28.8, p=55.2, fl=20, g=0, dir="concurrent", ref="saffire46"),
 dict(name="LUCI (fabric)", mat="Cotton-fibreglass fabric", o2=21.0, p=101.3, fl=0, g=0.165, dir="simulated lunar gravity", ref="luci"),
 dict(name="LUCI (rod)", mat="4 mm PMMA rod", o2=21.0, p=101.3, fl=0, g=0.165, dir="simulated lunar gravity", ref="luci"),
]

# ---------------------------------------------------------------- report passages for the assistant
KW = ["flammab", "extinction", "extinguish", "limit", "oxygen", "smoke", "detector", "particle", "quench", "blowoff", "suppress", "ignition", "spread", "gravity", "conclusion", "result"]
SRC = [("PSI-25", "PSI-25_Reports_BASS-II Summary Report.txt", "BASS-II Summary Report", 34), ("PSI-102", "PSI-102_Reports_SAME_Final Science Report.txt", "SAME Final Science Report", 18),
       ("PSI-101", "PSI-101_Reports_SAME-R_Final Report.txt", "SAME-R Final Report", 14), ("PSI-159", "PSI-159_Reports_FinalRpt_ACME.CFI-G.txt", "ACME CFI-G Final Report", 10),
       ("PSI-39", "PSI-39_Reports_CFI Science Final Report.txt", "CFI Science Final Report", 6), ("PSI-107", "PSI-107_Reports_SPICE_FinalReport.txt", "SPICE Final Report", 8),
       ("PSI-47", "PSI-47_Reports_DAFT_FinalReport.txt", "DAFT Final Report", 6), ("PSI-26", "PSI-26_Science Documents_SRD_BASS.txt", "BASS Science Requirements", 5),
       ("PSI-25", "PSI-25_Science Documents_BASS-II_ReadMe.txt", "BASS-II ReadMe", 6)]
passages = []
for pid, fn, label, k in SRC:
    p = os.path.join(BASE, "documents_text", fn)
    if not os.path.exists(p): continue
    txt = open(p, encoding="utf-8", errors="ignore").read()
    paras = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"\n\s*\n", txt)]
    cand = []
    for x in paras:
        if not (260 <= len(x) <= 1100): continue
        if sum(ch.isdigit() for ch in x) > len(x) * 0.18 or x.count("....") > 2: continue
        if re.search(r"\b(Ref\.|pp\.|vol\.)\s*\d+.*\b(pp\.|vol\.)", x) and len(re.findall(r"\b(19|20)\d\d\b", x)) > 3: continue
        low = x.lower(); sc = sum(low.count(k_) for k_ in KW) / (len(x) / 400)
        cand.append((sc, x))
    cand.sort(reverse=True)
    for sc, x in cand[:k]:
        passages.append([ORDER.index(pid), label, x[:900]])

bundle = dict(built=BUILT, checked=CHECKED, TF=TF, tests=tests, inv=inv, raw=raw, env=ENV, ext=EXT,
              extTests=EXT_TESTS, meas=MEAS, passages=passages)
s = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).replace("�", "")
open(OUT, "w", encoding="utf-8").write(s)
n_ind = sum(1 for t in tests if t[IND_I] == 1)
print("bytes", len(s), "rows", len(tests), "individual tests", n_ind, "inv", len(inv), "raw", len(raw), "passages", len(passages))
print("pressure states", collections.Counter(t[TF.index("pstate")] for t in tests))
for v in inv: print(v["id"], v["acr"][:22], f"{v['nind']}/{v['n']}", v["st"], v["o2"], v["p"], v["fl"])
