# Labeling handoff

The project team has checked and verified the outcome labels, as confirmed by
the project owner. Initial annotation provenance is retained in the reviewer
fields. Unresolved evidence remains unresolved. Team verification does not imply
NASA approval of the app or its predictions. Annotations are curated records,
not a keyword classifier. Each is keyed
by stable experiment ID and hashes the original note, conditions and description.
The builder fails if those source fields change after review.

`solid_test_reviews.jsonl` contains test outcomes, causes, any-flame labels,
context flags and reviewer provenance. `solid_stage_reviews.jsonl` contains 91
specific event-to-flow links, each with a verbatim evidence span and its source
field. These are the editable source inputs. Do not edit generated clean files.

## Targets and files

| File in `data/clean/` | Meaning |
| --- | --- |
| `solid_combustion_model.csv` | Original 250 whole tests plus reviewed summaries. `burned_binary=1` means some visible flame was reported during the test, including brief ignition. It is not a sustained-burning target. |
| `label_review_queue.csv` | Completed review worksheet with labels or explicit unresolved status. Condition fields remain blank because a whole changing-flow test has no single outcome condition. |
| `airflow_readings.csv` | Conservative parsing of recorded airspeed lists. Reading order is not a timestamp. Outcomes are deliberately unassigned until a note links an event to a reading. |
| `solid_stage_observations.csv` | Evidence-linked events, terminal outcomes, unknown flows and exclusion reasons. Burnout and deliberate suppression are retained as observed events. |
| `solid_stage_training.csv` | Conservative candidates for a source-reported sustained-flame stage classifier, screened for measured flow, material identity, sensor changes and confounding. |
| `flex_labeled.csv` | All 274 droplet tests; disruptions are censored with blank classification target. |
| `flex_training.csv` | 202 screened droplet candidates: 176 extinction and 26 completion. Disruptions, missing features, nonpositive pressure and inconsistent gas totals are excluded. |
| `labeling_report.json` | Counts, class balance, exclusions and feature whitelists. |

The current solid subset has 47 stages (31 sustained, 16 not sustained), grouped
into 41 conservative sample groups. Use the generated report for authoritative
counts after any review changes. The labeled subset is small and exploratory;
it does not establish that the proposed advisor model is feasible or accurate.

## Interpretation rules

- A flame that burned and then extinguished contributes two different events.
  Its final extinction does not turn its earlier burn into a negative.
- `sustained_flame_binary` reflects the source's reported sustained/established
  flame versus failed sustain or extinction at an identified event. Reports have
  different observation durations; this is not a uniform 30-second burn test.
- `protocol=ignition_trial` and `protocol=ongoing_burn_trial` describe the setup
  before observing the result. Both include positive and negative outcomes.
  An ongoing-burn extinction model cannot be presented as ignition resistance.
- `oxygen_initial_pct` is the measured initial test atmosphere. Actual oxygen
  at a later stage is **unknown**, left blank, and never interpolated. Rows with
  reported initial-to-final differences over 0.5 percentage points are excluded
  as a conservative screening heuristic, not a sensor accuracy specification.
  Smaller differences do not prove constant oxygen. Nitrogen-intervention cases
  are excluded unless the particular reviewed case describes a completed prefill.
- Fan voltage, potentiometer positions, airspeed, bounds and uncertain text are
  distinct. Extinction at pot 0.35 does not mean extinction at 0.35 cm/s. A zero
  anemometer display also need not mean zero physical airflow.
- No outcome is copied to every item of an airflow list. Some entries remain
  unsplit when units or ordering are mixed. Missing flow-to-outcome evidence
  requires further source/video analysis; it cannot be recovered by more parsing.
- Hardware failure, exhausted fuel, geometry changes, source/date conflicts,
  missing observations and unresolved conditions remain flagged. Brief ignition
  establishes an any-flame observation, not sustained burning.

## Model lead

Step 2 selected `flex_training.csv` for the one exploratory model; see
[MODEL_SCOPE.md](../../docs/MODEL_SCOPE.md) and `model/model_spec.json`.
Solid stage candidates remain available for research and future label review.
Never pool droplets with solids. Use the selected model specification's feature
whitelist; the CSVs also carry outcome-related evidence columns for
audit, and those columns must not be used as features. Final gas composition,
burn time, extinction diameter, source notes, labels and event descriptions can
leak the answer. Keep whole-test summaries out of a condition-specific model.

For solids, group cross-validation by `validation_group`, which conservatively
joins BASS/BASS-II sample numbers and strips a trailing modified-sample `m`.
This can overgroup different samples but avoids treating plausible repeat burns
as independent tests. FLEX retains `split_group` based on the original source
identifier. Check groups and class support in each fold; stage count is not the
independent-sample count. Missing dimensions/pressure remain missing. A nominal
diameter need not describe the actual remaining size of a repeatedly burned rod.

The FLEX target is `extinction_binary`: recorded Extinction (1) versus Completion
(0), conditional on those two observable endings. It is not an ignition or
suppression-success label, and disruption exclusion creates a selection limit.

Run `python3 data/scripts/label_data.py` to apply the reviews without downloading
anything or reading the PDFs. Then rerun `audit_model_readiness.py` to refresh the
selected model specification. The full `build_data.py` runs both after rebuilding
observations. These builds are deterministic. Review the evidence spans and
any pilot model errors before making engineering claims. No model was trained
by this labeling step.
