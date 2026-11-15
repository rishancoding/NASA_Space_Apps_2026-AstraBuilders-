# Prediction and evidence limits

The UI and API use the same coverage rules. They do not certify spacecraft or material safety.

## FLEX coverage and controls

Only `flex_training.csv` supplies model-support neighbours. Disruptions, missing inputs and failed physical-quality checks cannot provide support. The 202 screened rows retain NASA's recorded `Extinction`/`Completion` categories. `Completion` is not expanded into a physical endpoint without a source definition.

An estimate requires all of the following:

- Valid physical inputs and a nonnegative nitrogen remainder.
- Each feature inside its published per-fuel range.
- At least three distinct `split_group` values nearby, using the same fuel and gas family (oxygen/nitrogen, CO₂ dilution, helium dilution, or a mixture only if represented).
- A passing model promotion gate.

“Nearby” means a Euclidean distance at most 1.5 over the five numeric inputs, scaled by standard deviations of the screened training set. This is an explicit conservative heuristic, not an independently validated accuracy boundary. Coverage is not a guarantee of accuracy; methanol has only eight Completion examples. Three repeat burns from one sample count as one group.

`GET /api/options` returns supported starting NASA tests. `POST /api/predict/controls` accepts the same inputs as the predictor and returns discrete supported values for each feature with the other inputs fixed. Values are filtered by physical, range, gas-family and group-density checks. The UI uses these values instead of free-form numeric inputs or independent global sliders. After every change the allowed values are recomputed. Gaps are not selectable. Changing fuel or mixture resets the full scenario to an actual supported NASA test. Users can reset or open that source test.

Both prediction endpoints, the assistant tools and every what-if point enforce coverage again. Unsupported inputs return `available: false`, a reason and nearby evidence, with no prediction value or interval. Model sensitivity comparisons outside coverage are omitted.

## Solid evidence comparisons

Materials are ranked only by the amount and proximity of evidence, not by a fraction of flame outcomes. Geometry and optional maximum thickness apply to whole-test matches and their stage events. Unknown thickness cannot satisfy a numeric thickness limit. Airflow proximity uses exact recorded readings, without interpolating between sequence entries.

Ignition trials and already-burning trials are counted separately; `protocol` selects the event summary (default `ignition_trial`). Supporting stage IDs and quotations are returned with each summary. Whole-test outcomes remain explicitly separate from results linked to an airflow stage. Matching uses initial test oxygen; oxygen at the event is unknown. Observation durations vary, and counts are not comparable material safety rates.

The dataset has no Moon/Mars partial-gravity tests. Behaviour there is unknown; microgravity and Earth observations do not establish upper or lower bounds.

## Burn-time intervals

`python3 model/train_flex.py --task burn-time` rebuilds only the corrected burn-time pipeline. The classifier is retained. Full retraining without this flag rebuilds both models.

A fixed group-disjoint split uses seeds 42 and 43: approximately 60% of groups for fitting and candidate selection, 20% for calibration and 20% for audit. Candidate selection uses five-fold grouped CV within fitting rows only. Preprocessing and the final selected model fit only on fitting rows. The deployed pipeline is never refit on calibration or audit rows.

Calibration uses one score per sample group: the maximum absolute log-space prediction error among that group's burns. For n calibration groups the nominal 90% radius is the `ceil((n+1)*0.9)`-th ordered score, without interpolating percentiles. Too few groups to obtain a finite radius cause training to fail. This follows the independent calibration and finite-sample quantile procedure described in [Angelopoulos and Bates](https://arxiv.org/abs/2107.07511), using grouped maximum residuals to keep repeat observations together. Group splitting uses [scikit-learn GroupShuffleSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html).

The independent audit does not influence fitting, candidate choice or calibration. Promotion requires an audit R² lower 95% group-bootstrap bound above 0.2 and at least 85% empirical group interval coverage. A failing gate disables burn-time estimates. Nominal coverage is marginal under exchangeable sample groups, not guaranteed at every fuel/atmosphere or under distribution shift. This retrospective split of a small historical dataset is not prospective validation.

The current artifact has 119 fitting rows, 41 calibration rows and 40 audit rows. Audit R² is 0.612 (group-bootstrap interval approximately 0.36–0.81), mean absolute error 2.90 seconds, and 36/40 audit groups covered by the nominal 90% interval. Model/interval metrics are retained in `metrics.json`, partition membership in both metrics and the joblib artifact, and audit-only burn-time predictions in `oof_predictions.json` under its legacy `burn_time` key.

Historical `evaluation.json` stress tests describe full-dataset CV candidates from the earlier run. They do not evaluate the frozen pipeline or calibrate its intervals; the UI labels them accordingly. The primary burn-time metrics are now the separate audit results.

## Official and experimental entry points

React/FastAPI is the official submission app. The Streamlit reference retains different historical classifiers and scores; it is not the submission launcher. Both use `api.core.check_flex_domain` for physical validity, per-fuel ranges, gas family and nearby-group support. The archived solid predictor also withholds unsupported numbers at its backend boundary. UI cards show “Unavailable” and sweeps leave gaps, so callers cannot bypass a warning to display an out-of-domain percentage. These changes do not promote the experimental solid classifier into the official Material Advisor.

`/api/model` also reports `per_fuel_validation` computed from the current selected classifier's saved out-of-fold predictions. Current warnings use these figures; historical full-dataset stress-test scores remain explicitly separate.

## Fixed material-ranking disclosure

The advisor has one fixed method (`evidence_strength`), with no ranking selector. It restores the original order: sum `exp(-distance)` across nearby whole tests and sort highest first. More comparable tests and closer conditions both increase the evidence score. Geometry/thickness filtering applies before ranking. Flame-outcome proportions do not affect the order.

The UI explains this above the results and provides the calculation in a disclosure. Every material has a short rank explanation; analyze mode may pin the selected material while preserving its computed rank. This is an evidence ranking, not a safety ranking. The former user-selectable and safety-screening modes are removed.
