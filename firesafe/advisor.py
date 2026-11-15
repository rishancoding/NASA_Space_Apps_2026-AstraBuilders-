"""Material Safety Advisor: matches a scenario to NASA tests, scores and ranks materials.

All numbers and the ranking are computed here, deterministically, from the tables
and the trained model. The LLM only explains this output.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from . import predictor
from .data import (GROUND_FAMILY, PSI_URL, UNRESOLVED, ground, materials, saffire, solid_training, solids,
                   test_airflow_values)

MISSIONS = {
    "Space station (microgravity)": "microgravity",
    "Moon base (1/6 g)": "lunar",
    "Mars habitat (3/8 g)": "martian",
}
PRIORITIES = {
    "sustained": "Resist sustained burning",
    "ignition": "Resist ignition",
    "spread": "Minimize flame spread",
    "evidence": "Strongest comparable NASA evidence",
}
GEOMETRIES = ["any", "fabric", "film", "sheet", "slab", "rod", "sphere", "candle"]
O2_TOL = 1.5        # percentage points
AIR_TOL = 0.5       # +/- 50% of the requested airflow (min 3 cm/s)


@dataclass
class Scenario:
    mode: str = "discover"                 # "analyze" | "discover"
    mission: str = "Space station (microgravity)"
    oxygen_pct: float = 21.0
    pressure_kpa: float = 101.3
    airflow_cm_s: float = 10.0
    material: str | None = None
    purpose: str = ""
    geometry: str = "any"
    thickness_mm: float | None = None
    max_thickness_mm: float | None = None
    max_mass_kg: float | None = None
    budget: float | None = None
    other_requirements: str = ""
    priority: str = "sustained"
    require_geometry: bool = False
    require_nearby_tests: bool = False


@dataclass
class Check:
    name: str
    status: str            # "meets" | "fails" | "cannot assess" | "outside data"
    detail: str


@dataclass
class Candidate:
    material: str
    rank: int | None = None
    is_selected: bool = False
    evidence_strength: str = "none"
    match: str = "none"
    comparable_tests: list = field(default_factory=list)
    stage_evidence: dict = field(default_factory=dict)
    prediction: dict | None = None
    prediction_scenario: str | None = None
    saffire: list = field(default_factory=list)
    ground: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    concerns: list = field(default_factory=list)
    citations: list = field(default_factory=list)
    sort_value: float | None = None
    scenario_oxygen: float = 0.0
    scenario_airflow: float = 0.0
    sort_basis: str = ""
    excluded_reason: str | None = None


def _air_ok(values: list[float], target: float) -> bool:
    tol = max(3.0, AIR_TOL * target)
    return any(abs(v - target) <= tol for v in values)


def comparable_tests(material: str, oxygen: float, airflow: float) -> tuple[list[dict], str]:
    """Tests of this material near the oxygen level; 'close' if airflow also matches."""
    s = solids()
    rows = s[(s["material"] == material) & ((s["oxygen_pct"] - oxygen).abs() <= O2_TOL)]
    flows = test_airflow_values()
    out = []
    for r in rows.itertuples():
        vals = flows.get(r.experiment_id, [])
        out.append({
            "experiment_id": r.experiment_id, "source_record": r.source_record,
            "investigation": r.investigation_name, "test_id": r.test_id, "material_raw": r.material_raw,
            "geometry": r.sample_geometry, "oxygen_pct": r.oxygen_pct,
            "airflow_readings_cm_s": vals, "airflow_raw": r.airflow_raw if isinstance(r.airflow_raw, str) else "",
            "airflow_match": bool(vals) and _air_ok(vals, airflow),
            "outcome": r.outcome, "outcome_group": r.outcome_group,
            "notes": r.notes[:400], "source_url": r.source_url,
            "locator": f"{r.source_file} row {r.source_row}",
        })
    close = [t for t in out if t["airflow_match"]]
    if close:
        return close + [t for t in out if not t["airflow_match"]], "close"
    return out, ("oxygen only" if out else "none")


def stage_evidence(material: str, oxygen: float, airflow: float) -> dict:
    """Verified-condition stages (training set) near the scenario: how often the flame stayed lit."""
    d = solid_training()
    d = d[(d["material"] == material) & ((d["oxygen_initial_pct"] - oxygen).abs() <= O2_TOL)]
    d = d[[_air_ok([a], airflow) for a in d["airflow_cm_s"]]] if len(d) else d
    out = {}
    for proto, g in d.groupby("protocol"):
        out[proto] = {"n": int(len(g)), "sustained": int(g["sustained_flame_binary"].sum())}
    return out


def _strength(tests: list[dict], match: str, stages: dict) -> str:
    n_close = sum(t["airflow_match"] for t in tests)
    n_stage = sum(v["n"] for v in stages.values())
    if match == "close" and (n_close >= 5 or n_stage >= 3):
        return "strong"
    if match == "close" or len(tests) >= 3:
        return "moderate"
    if tests:
        return "weak"
    return "none"


def _ground_rows(material: str) -> list[dict]:
    fam = GROUND_FAMILY.get(material)
    if not fam:
        return []
    g = ground()
    g = g[g["material"] == fam]
    return [{"configuration": r.configuration, "uloi_oxygen_pct": r.uloi_oxygen_pct, "moc_oxygen_pct": r.moc_oxygen_pct,
             "thickness_mm": r.thickness_mm, "table": r.table_number, "pdf_page": r.pdf_page,
             "source_url": r.source_url} for r in g.itertuples()]


def _checks(sc: Scenario, material: str, tests_all) -> list[Check]:
    gravity = MISSIONS.get(sc.mission, "microgravity")
    checks: list[Check] = []
    oxy = tests_all["oxygen_pct"].dropna()
    if len(oxy):
        lo, hi = oxy.min(), oxy.max()
        st = "meets" if lo - 0.5 <= sc.oxygen_pct <= hi + 0.5 else "outside data"
        checks.append(Check("Oxygen", st, f"Tested at {lo:.1f}-{hi:.1f}% O2; you entered {sc.oxygen_pct:g}%."))
    elif material == "Silicone":
        checks.append(Check("Oxygen", "meets" if abs(sc.oxygen_pct - 22) <= O2_TOL else "outside data",
                            "Saffire-II samples only, at about 21.5-22.1% O2."))
    flows = [v for eid in tests_all["experiment_id"] for v in test_airflow_values().get(eid, [])]
    if material == "Silicone":
        flows = [20.0]
    if flows:
        lo, hi = min(flows), max(flows)
        checks.append(Check("Airflow", "meets" if lo <= sc.airflow_cm_s <= hi else "outside data",
                            f"Tested at {lo:g}-{hi:g} cm/s; you entered {sc.airflow_cm_s:g} cm/s."))
    pres = tests_all["pressure_kpa"].dropna()
    if len(pres) and pres.min() - 3 <= sc.pressure_kpa <= pres.max() + 3:
        checks.append(Check("Pressure", "meets", f"Recorded test pressures {pres.min():.0f}-{pres.max():.0f} kPa."))
    else:
        detail = (f"Recorded test pressures {pres.min():.0f}-{pres.max():.0f} kPa; you entered {sc.pressure_kpa:g} kPa."
                  if len(pres) else "No pressure recorded for this material's tests (BASS-II/Saffire tables list none).")
        checks.append(Check("Pressure", "outside data" if len(pres) else "cannot assess", detail))
    if gravity == "microgravity":
        checks.append(Check("Gravity", "meets", "All PSI solid tests ran in microgravity on the ISS or Cygnus."))
    else:
        checks.append(Check("Gravity", "cannot assess",
                            "No partial-gravity combustion data exists. Microgravity and Earth-gravity results "
                            "measure different things and do not bound lunar/Martian behaviour."))
    geoms = set(tests_all["sample_geometry"].dropna())
    if material == "Silicone":
        geoms = {"sheet"}
    if sc.geometry != "any":
        checks.append(Check("Shape", "meets" if sc.geometry in geoms else "fails",
                            f"Tested shapes: {', '.join(sorted(geoms)) or 'not recorded'}."))
    dims = np.concatenate([tests_all[c].dropna().values for c in ("thickness_mm", "diameter_mm")]) \
        if len(tests_all) else np.array([])
    if sc.thickness_mm is not None:
        if len(dims):
            ok = dims.min() * 0.5 <= sc.thickness_mm <= dims.max() * 2
            checks.append(Check("Thickness", "meets" if ok else "outside data",
                                f"Tested thickness/diameter {dims.min():g}-{dims.max():g} mm."))
        else:
            checks.append(Check("Thickness", "cannot assess", "No thickness recorded for these tests."))
    if sc.max_thickness_mm is not None:
        if len(dims):
            ok = dims.min() <= sc.max_thickness_mm
            checks.append(Check("Max thickness", "meets" if ok else "fails",
                                f"Thinnest tested sample {dims.min():g} mm vs your limit {sc.max_thickness_mm:g} mm "
                                "(evidence exists at or below your limit)" if ok else
                                f"Every tested sample was thicker than {sc.max_thickness_mm:g} mm, so no NASA "
                                "evidence covers a part within your limit."))
        else:
            checks.append(Check("Max thickness", "cannot assess", "No thickness recorded for these tests."))
    if sc.max_mass_kg is not None:
        checks.append(Check("Max mass", "cannot assess", "PSI records no density or mass data."))
    if sc.budget is not None:
        checks.append(Check("Budget", "cannot assess", "PSI records no cost data."))
    if sc.other_requirements.strip():
        checks.append(Check(f"Requirement: {sc.other_requirements.strip()[:60]}", "cannot assess",
                            "PSI combustion data has no mechanical, thermal or electrical property data."))
    return checks


def _evaluate(sc: Scenario, material: str) -> Candidate:
    s = solids()
    tests_all = s[s["material"] == material]
    c = Candidate(material=material, is_selected=(sc.mode == "analyze" and material == sc.material),
                  scenario_oxygen=sc.oxygen_pct, scenario_airflow=sc.airflow_cm_s)
    c.comparable_tests, c.match = comparable_tests(material, sc.oxygen_pct, sc.airflow_cm_s)
    c.stage_evidence = stage_evidence(material, sc.oxygen_pct, sc.airflow_cm_s)
    c.saffire = saffire(material)
    c.ground = _ground_rows(material)
    if material == "Silicone" and c.saffire:
        near = abs(sc.oxygen_pct - 22) <= O2_TOL and _air_ok([20.0], sc.airflow_cm_s)
        c.match = "close" if near else "none"
    c.evidence_strength = _strength(c.comparable_tests, c.match, c.stage_evidence)
    if material == "Silicone" and c.match == "close":
        c.evidence_strength = "weak"   # four small Saffire-II samples, one condition
    gravity = MISSIONS.get(sc.mission, "microgravity")

    # Model estimate for the scenario that matches the priority.
    if material in predictor.solid_materials():
        tested = predictor.metrics()["solid"]["protocols_by_material"][material]
        want = "ignition_trial" if sc.priority == "ignition" else "ongoing_burn_trial"
        proto = want if want in tested else tested[0]
        c.prediction = predictor.predict_solid(material, sc.oxygen_pct, sc.airflow_cm_s, proto,
                                               sc.pressure_kpa, gravity)
        c.prediction_scenario = proto
        if proto != want:
            c.concerns.append(f"{material} was never tested as '{predictor.PROTOCOLS[want]}', so its estimate uses "
                              f"'{predictor.PROTOCOLS[proto]}' and is not directly comparable.")
    c.checks = _checks(sc, material, tests_all)

    # Concerns and limitations.
    if c.evidence_strength in ("weak", "none"):
        c.concerns.append("Few or no NASA tests near your conditions.")
    variants = sorted(set(tests_all["material_raw"]))
    if len(variants) > 3:
        c.concerns.append(f"Results pool {len(variants)} sample variants (shape, colour, thickness); a shared name "
                          "does not mean equal flammability.")
    if len(tests_all):
        c.concerns.append("Outcome labels were reviewed by an AI from crew/report notes, without human sign-off.")
    if gravity != "microgravity":
        c.concerns.append("Your mission gravity was never tested.")
    if c.prediction and c.prediction["warnings"]:
        c.concerns += [w for w in c.prediction["warnings"] if w not in c.concerns]

    # Citations: investigations, a few test rows, Saffire rows, ground tables.
    seen = set()
    for t in c.comparable_tests[:6]:
        c.citations.append({"label": f"{t['investigation']} test {t['test_id']} ({t['locator']})", "url": t["source_url"]})
        seen.add(t["source_record"])
    for rec in sorted(set(tests_all["source_record"]) - seen):
        c.citations.append({"label": f"{rec} investigation record", "url": PSI_URL.format(rec)})
    for r in c.saffire:
        c.citations.append({"label": f"{r['source_record']} Saffire sample {r['sample']}", "url": r["source_url"]})
    if c.ground:
        c.citations.append({"label": "NTRS 20110008636 Tables 2-9 (Earth gravity, comparison only)",
                            "url": c.ground[0]["source_url"]})
    return c


def _sort(c: Candidate, priority: str) -> tuple:
    tier = {"strong": 0, "moderate": 1, "weak": 2, "none": 3}[c.evidence_strength]
    if priority == "evidence":
        n = sum(t["airflow_match"] for t in c.comparable_tests) * 10 + len(c.comparable_tests)
        c.sort_value, c.sort_basis = float(n), "comparable NASA tests (airflow-matched weighted x10)"
        return (tier, -n)
    if priority == "spread":
        # Saffire-II (PSI-99) is the only curated flame-spread measurement: 20 cm/s, ~22% O2.
        # 0 = did not ignite or spread, 1 = burned with an anchored flame, 2 = spread 2.1 mm/s.
        spread = {"Silicone": (0, "did not burn (samples 2-1..2-4)"),
                  "Nomex": (0, "not ignited beside burning PMMA (sample 2-7)"),
                  "PMMA": (1, "burned 600 s with the flame anchored, regression 0.01-0.04 mm/s (sample 2-8)"),
                  "SIBAL (cotton/fiberglass)": (2, "spread 2.1 mm/s over the full 29 cm (sample 2-5)")}
        near = abs(c.scenario_oxygen - 22.0) <= O2_TOL and _air_ok([20.0], c.scenario_airflow)
        if c.material in spread and near:
            c.sort_value, why = spread[c.material]
            c.sort_basis = f"Saffire-II at 20 cm/s, ~22% O2: {why}"
            return (0, c.sort_value, tier)
        c.sort_basis = ("no flame-spread measurement for this material" if c.material not in spread else
                        "Saffire-II spread data exists only at 20 cm/s and ~22% O2, not near your conditions")
        return (1, tier)
    p = c.prediction["probability"] if c.prediction else None
    if p is None or c.match == "none":
        c.sort_basis = ("no comparable tests near your conditions" if c.match == "none" else
                        "no model estimate (material not in the model's training stages)")
        return (4, tier)
    c.sort_value = p
    c.sort_basis = f"model estimate of sustained burning ({predictor.PROTOCOLS[c.prediction_scenario]})"
    # Evidence tier first, so a thinly evidenced low estimate never outranks a well-evidenced one.
    return (min(tier, 2), p)


def advise(sc: Scenario) -> dict:
    cands = [_evaluate(sc, m) for m in materials() if m != UNRESOLVED]
    kept, excluded, selected = [], [], []
    for c in cands:
        if c.is_selected:
            selected.append(c)
            continue
        if sc.require_geometry and any(ch.name == "Shape" and ch.status == "fails" for ch in c.checks):
            c.excluded_reason = f"never tested as {sc.geometry}"
        elif sc.require_nearby_tests and c.match == "none":
            c.excluded_reason = "no NASA tests near your oxygen level"
        elif any(ch.name == "Max thickness" and ch.status == "fails" for ch in c.checks):
            c.excluded_reason = "no tested sample within your maximum thickness"
        (excluded if c.excluded_reason else kept).append(c)
    kept.sort(key=lambda c: _sort(c, sc.priority))
    for i, c in enumerate(kept, 1):
        c.rank = i
    for c in excluded + selected:
        _sort(c, sc.priority)

    # Pairwise claims are only made when both sides have adequate, comparable evidence.
    comparisons = []
    ranked = [c for c in selected + kept if c.sort_value is not None]
    for a, b in zip(ranked, ranked[1:]):
        same_basis = a.prediction_scenario == b.prediction_scenario
        enough = a.evidence_strength in ("strong", "moderate") and b.evidence_strength in ("strong", "moderate")
        gap = abs((b.sort_value or 0) - (a.sort_value or 0))
        supported = same_basis and enough and gap >= 0.25 and sc.priority in ("sustained", "ignition")
        if sc.priority == "spread":
            same_basis, enough = True, True
            supported = a.sort_value != b.sort_value   # one Saffire sample each: report, but call it single-test
        if sc.priority == "evidence":
            supported = False
        comparisons.append({"higher": a.material, "lower": b.material, "supported": supported,
                            "reason": ("single Saffire-II sample each at one condition" if sc.priority == "spread"
                                       and supported else
                                       "ranking by amount of evidence, not by safety" if sc.priority == "evidence" else
                                       "both well evidenced, same test scenario, large gap") if supported or
                            sc.priority == "evidence" else
                            "not supported: " + ("different test scenarios" if not same_basis else
                                                 "thin evidence on one side" if not enough else
                                                 "difference too small" if gap < 0.25 else
                                                 "this priority has no comparable measurement")})
    return {
        "scenario": asdict(sc),
        "gravity": MISSIONS.get(sc.mission, "microgravity"),
        "priority_label": PRIORITIES[sc.priority],
        "selected": [asdict(c) for c in selected],
        "candidates": [asdict(c) for c in kept],
        "excluded": [asdict(c) for c in excluded],
        "comparisons": comparisons,
        "unassessable_constraints": sorted({ch.name for c in selected + kept for ch in c.checks
                                            if ch.status == "cannot assess"}),
        "disclaimer": "Ranks order PSI-tested materials by the chosen priority and evidence strength. They are not a "
                      "safety certification; a material is only called better than another where the comparison "
                      "row says the evidence supports it.",
    }


def summary_text(result: dict) -> str:
    """Plain deterministic explanation, used when no LLM is configured."""
    sc = result["scenario"]
    lines = [f"Scenario: {sc['oxygen_pct']:g}% O2, {sc['airflow_cm_s']:g} cm/s airflow, {sc['pressure_kpa']:g} kPa, "
             f"{sc['mission']}. Priority: {result['priority_label']}."]
    for c in result["selected"] + result["candidates"]:
        est = (f"model estimate {c['prediction']['probability']:.0%} chance of sustained burning"
               if c.get("prediction") and c["prediction"].get("probability") is not None else "no model estimate")
        n = len(c["comparable_tests"])
        head = "Your material" if c["is_selected"] else f"{c['rank']}."
        lines.append(f"{head} {c['material']}: {c['evidence_strength']} evidence ({n} comparable "
                     f"test{'s' if n != 1 else ''}, match: {c['match']}); {est}. Ranked by: {c['sort_basis']}.")
    sup = [x for x in result["comparisons"] if x["supported"]]
    lines.append("Supported comparisons: " + ("; ".join(f"{x['higher']} ranked above {x['lower']}" for x in sup)
                                              if sup else "none. The evidence does not establish that any one "
                                                          "material is safer than the next."))
    if result["unassessable_constraints"]:
        lines.append("Could not be checked with PSI data: " + ", ".join(result["unassessable_constraints"]) + ".")
    return "\n\n".join(lines)
