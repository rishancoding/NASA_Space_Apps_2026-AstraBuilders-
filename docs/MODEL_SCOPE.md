# Step 2 — prediction target and supported scope

**Decision:** use the FLEX fallback already specified in the team's plan for the
one exploratory learned model. Keep solid-material comparisons based on observed
NASA evidence. No model was trained in this step.

The reproducible audit is [model_readiness.json](../data/clean/model_readiness.json).
The machine-readable handoff to Step 3 is [model_spec.json](../model/model_spec.json).
Run `python3 data/scripts/audit_model_readiness.py` after changing labels.

## Why the solid-fuel predictor is not selected

The 47 stage candidates combine 23 ignition-trial observations (10 positive,
13 negative) with 24 ongoing-burn observations (21 positive, only 3 negative).
Pooling these does not establish a single consistent material burn/no-burn
endpoint. Observation durations vary: a negative PMMA M9 event describes a flame
going out after 15 minutes at 14 cm/s, whereas other records describe brief
ignition failures. Initial oxygen is also a proxy for unknown later-stage oxygen.

Thickness and diameter are each missing in 40 of 47 stages; width is missing in
26. Ultem has only negative observations and Japan wax only positive ones.
Material, size, protocol and conditions are not sufficiently crossed to claim a
general ranking of intrinsic material safety. This is a feasibility decision
based on coverage and label meaning, not a claim that a fitted model performed
badly. The test/stage annotations remain available for exploration and future
review. Do not train on the 250 whole-test any-flame flags as condition labels.

## Selected target

Use PSI-69's recorded **Test end** categories:

- `extinction_binary = 1`: the source records **Extinction**.
- `extinction_binary = 0`: the source records **Completion**.
- **Disruption**: censored/excluded, not assigned either class.

The future output is an experimental estimate of the recorded extinction-versus-
completion category among comparable, non-disrupted FLEX observations. Do not
relabel it as ignition probability, a general suppression-success probability,
solid-material burn risk, or a causal treatment effect. Use the source's literal
category names; do not infer an undocumented definition of Completion.

## Quality review and exclusions

The original FLEX data contains 274 tests. The initial candidate filter produced
207 rows after excluding 61 disruptions and 6 incomplete-feature records.
Step 2 additionally excludes these **five source records**, without changing
their reported measurements or outcome labels:

| Test | Identifier | Reason |
| --- | --- | --- |
| 114 | C11M201 | Reported initial pressure is zero mmHg; no physical default was substituted. |
| 69 | 193R002 | Reported initial gas fractions total 0.98. |
| 75 | 203R002 | Reported initial gas fractions total 0.98. |
| 76 | 203F001 | Reported initial gas fractions total 0.98. |
| 79 | 179F001 | Reported initial gas fractions total 0.98. |

Source-composition sums must be within 0.01 of one, allowing a small floating-
point margin. This is a conservative data-screening choice, not an assertion of
instrument accuracy. Positive finite pressure/diameter and valid fractions are
also required. Source values remain in `flex_backup.csv` and `flex_labeled.csv`;
the latter records each exclusion reason. No fractions are renormalized.

The selected CSV now contains **202 rows: 176 Extinction and 26 Completion**, in
201 source-identifier groups. Always predicting Extinction would give about
87.1% raw accuracy on these labels, so raw accuracy alone is not a useful success
criterion. This is a count-based reference, not a trained-model result.

## Inputs

| Feature | Meaning / unit |
| --- | --- |
| `fuel` | Methanol or Heptane; categorical |
| `oxygen_pct` | Initial oxygen mole percent |
| `pressure_kpa` | Initial absolute pressure, kPa |
| `co2_fraction` | Initial CO2 mole fraction |
| `helium_fraction` | Initial helium mole fraction |
| `droplet_diameter_mm` | Initial liquid-droplet diameter, mm |

Reported nitrogen is checked for mixture consistency but omitted from model
features because it is compositionally redundant. Scenario nitrogen is the
remaining fraction after oxygen, CO2 and helium. These are **droplet** inputs;
there is no solid-material selector, sheet-thickness slider, airflow feature or
lunar/Martian gravity parameter in this model. Pressure support here does not
create pressure support for BASS/BASS-II.

Per-fuel observed ranges are recorded in `model_spec.json`. They provide an
initial rejection boundary, not proof that every combination inside the ranges
has experimental support. The later backend must check comparable observations
jointly and flag unsupported inputs. Missing values must not silently become zero.

## Step 3 handoff

Compare logistic regression and a small random forest against a majority-class
baseline. Use five outer stratified group folds with a fixed seed, keep every
source identifier in one fold, and confirm both classes occur in each fold.
Fit preprocessing within each training fold. Tuning, calibration and threshold
selection must not use the held-out fold's labels.

Use balanced accuracy as the primary comparison, with macro F1, per-class
precision/recall/F1, confusion matrices and probability-quality checks. Report
uncertainty and the minority-class sample count. If validation does not support
useful estimates, keep numerical prediction unavailable rather than presenting
uncalibrated scores as reliable probabilities. Save only one selected final model.

Never use Test end, burn time, extinction diameter, burning-rate measurements,
identifiers, dates, annotations, eligibility flags or exclusion reasons as model
features. They are outcomes, provenance or possible leakage. Do not mix FLEX,
BASS, Saffire or Earth-gravity thresholds into one training table.

The later Material Advisor can still retrieve solid-fuel experiments and rank
their relevance/evidence strength. It must not use this droplet model to rank
spacecraft plastics or declare a material safest. This remains aligned with the
[official challenge](https://www.spaceappschallenge.org/2026/challenges/flame-in-freefall/),
which asks for investigation summaries, ranking and interpretation and does not
require a general material-safety ML classifier.

Validation references: [group-stratified splitting](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html)
and [classification metrics](https://scikit-learn.org/stable/modules/model_evaluation.html).
