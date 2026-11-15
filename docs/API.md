# Backend API and models: guide for the UI

The backend is a FastAPI app over the NASA data in `data/clean/` and two trained
FLEX droplet models. Build any frontend (React, Vue, plain JS) against it.

## Run it

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -r api/requirements.txt      # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m uvicorn api.main:app --reload --port 8000
```

Open **http://localhost:8000/docs**: every endpoint, with a "Try it out" button.
For TypeScript types, generate from the schema:

```sh
npx openapi-typescript http://localhost:8000/openapi.json -o src/api-types.ts
```

Chat needs one language-model key, set before starting the server. Everything
else works without it.

| Provider | Set | Default model | Cost per 1M tokens (input / output) |
| --- | --- | --- | --- |
| DeepSeek (default when its key is set) | `DEEPSEEK_API_KEY` | `deepseek-flash` (DeepSeek-V4.1-Flash), non-thinking mode | $0.15–0.30 / $0.60–1.20 (off-peak is half price) |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-opus-5-5` | $4 / $20 |

`CHAT_PROVIDER=deepseek|anthropic` forces one; `CHAT_MODEL` overrides the model.
`GET /api/health` shows which provider and model are active.

```sh
export DEEPSEEK_API_KEY=...        # PowerShell: $env:DEEPSEEK_API_KEY="..."
``` `CORS_ORIGINS` (comma-separated) restricts which
frontends may call the API; it defaults to `*` for local development.

Tests: `.venv/Scripts/python -m pytest api/tests -q`.

## Three conventions that keep the UI simple

**1. Every number is an object.** Build one `<Value>` component and use it everywhere.

```json
{"value": 0.49, "unit": "probability", "trust": "model_estimate",
 "range": [0.37, 0.64], "source": {"record": "PSI-69", "url": "https://psi.nasa.gov/..."},
 "note": "Range = spread across models refit on resampled NASA tests"}
```

`trust` is one of `nasa_measured`, `ai_label`, `model_estimate`, `earth_reference`
or `no_data`. The text for each label is in `GET /api/options` → `trust_labels`.
Show it as a badge. `value` can be `null` with a `range`, for example a solid
test that ran at several airflows.

**2. Errors name the field.** Bad input returns HTTP 422:

```json
{"errors": [{"field": "oxygen_pct", "message": "Oxygen, CO₂ and helium add up to more than 100% of the gas"}]}
```

Put each message under the matching control. Chat without a key returns 503
with the same shape.

**3. No number outside the data.** Prediction endpoints return
`{"available": false, "reason": ..., "out_of_range": [...], "nearest_tests": {...}}`
when inputs are outside the tested range. Show the reason and the nearest real
tests instead of a number.

## Endpoints by page

| Page | Call | Use it for |
| --- | --- | --- |
| All | `GET /api/options` | Slider min/max/step/default/unit, fuels, materials, geometries, presets, missions, priorities, trust and outcome labels. Build forms from this; hardcode nothing. |
| All | `GET /api/health` | Whether each model and chat are available, to show or hide features. |
| Material Advisor | `POST /api/advisor` | Both modes. Returns ranked candidates with evidence counts, nearby outcomes, Earth references, constraint checks (`met`, `failed`, `cannot_check`), concerns and the closest tests, plus warnings (oxygen above any tested value, partial gravity). |
| Material Advisor | `POST /api/similar/solid` | "Closest NASA tests" list and coverage badge for oxygen + airflow. |
| Material Advisor | `GET /api/ground/{material}` | Earth-gravity oxygen limits beside the orbital tests (PMMA, Ultem). |
| Predictor | `POST /api/predict/extinction` | Chance a droplet flame ends in extinction, with range, driving factors, nearest tests and warnings. |
| Predictor | `POST /api/predict/burn-time` | Burn time with a nominal 90% independently calibrated group interval. |
| Predictor controls | `POST /api/predict/controls` | Conditional supported settings, with other inputs held fixed. |
| Predictor | `POST /api/what-if` | A curve for one slider: `curve[]` of `{x, y, low, high, in_tested_range}` and `real_tests[]` to plot as dots. Call on slider change (debounce about 150 ms). |
| Predictor | `POST /api/similar/flex` | Nearest real droplet tests. |
| Model page | `GET /api/model` | Metrics for every candidate model and baseline, fold checks, confusion matrix, and out-of-fold predictions for actual-vs-predicted charts. |
| Data Explorer | `GET /api/investigations`, `GET /api/investigations/{id}` | Cards for the 19 PSI investigations plus the Earth report, with objective, approach, tables and publications. |
| Data Explorer | `GET /api/experiments?dataset=solid\|flex&...` | Filtered, sorted, paginated test table (`total`, `page`, `items`). |
| Data Explorer | `GET /api/experiments/{experiment_id}` | Detail drawer: crew notes, stage events with evidence quotes, source links. IDs contain `:`; pass them as they are. |
| Data Explorer | `POST /api/compare` | Two tests side by side; `differences` lists the fields that differ. |
| Data Explorer | `GET /api/coverage?dataset=solid\|flex` | Every real test as a chart point (where NASA has data). |
| Search bar | `GET /api/search?q=` | NASA report passages with record, file, locator, link and a highlighted `snippet`. `caution` is set on planned-test text. |
| Research Assistant | `POST /api/chat` | `{"messages": [{"role": "user", "content": "..."}], "context": {...}}` → `{answer, citations[], tool_calls[]}`. Send the whole conversation each time. Put the current advisor inputs or the selected experiment in `context`, so "why is this ranked first?" works. |

Example requests:

```js
await fetch("/api/predict/extinction", {method: "POST", headers: {"content-type": "application/json"},
  body: JSON.stringify({fuel: "Methanol", oxygen_pct: 21, pressure_kpa: 101.3, droplet_diameter_mm: 2.5})});

await fetch("/api/advisor", {method: "POST", headers: {"content-type": "application/json"},
  body: JSON.stringify({mode: "discover", oxygen_pct: 21, airflow_cm_s: 10, mission: "space_station",
                        max_thickness_mm: 2, priority: "evidence_strength"})});
```

## Models (`model/`)

Retrain with `.venv/Scripts/python model/train_flex.py`. It rewrites `model/artifacts/`.

| Model | Data | Validation | Status |
| --- | --- | --- | --- |
| Extinction vs completion: unweighted logistic regression (chosen over balanced-weight LR and a small random forest by Brier score) | 202 FLEX tests (176 extinction / 26 completion) | Balanced accuracy 0.80 (95% CI 0.71–0.89) vs 0.50 for always guessing; ROC AUC 0.81; Brier 0.083 vs 0.112 for quoting the base rate. Probabilities are calibrated: tests given about 62% ended in extinction 61% of the time | Enabled |
| Burn time: random forest on log(seconds), selected within fitting rows | 119 fit / 41 calibration / 40 independent audit rows | Audit R² 0.612 (group-bootstrap CI 0.36–0.81), MAE 2.90 s; nominal 90% interval covered 36/40 audit groups | Enabled where coverage permits |
| Similarity | 250 solid tests; 202 screened FLEX rows of matching fuel/gas family | Distance in typical-difference units, with coverage levels `close`, `partial`, `none` | n/a |
| Evidence search | 757 NASA text passages | TF-IDF keywords + latent semantic analysis, built in memory at startup | n/a |

### Historical candidate accuracy stress tests (`model/evaluate_models.py` → `model/artifacts/evaluation.json`, also in `GET /api/model` → `stress_tests`)

| Check | Extinction model | Burn-time model |
| --- | --- | --- |
| 20 different CV shuffles | Balanced accuracy 0.73–0.81, AUC ≥ 0.79 | R² 0.70–0.78 |
| Shuffled-label test (200 runs) | Real AUC 0.81 vs 0.48 when labels are shuffled (p = 0.005) | n/a |
| Simple shortcut | Beats fuel-only (AUC 0.81 vs 0.63) | Beats the d² burning law (R² 0.73 vs 0.31) |
| Per fuel | Heptane AUC 0.85; methanol AUC 0.60 (only 8 completions) | Methanol R² 0.67, heptane 0.64 |
| Unseen gas mix (hold out every CO₂ or helium test) | Helium AUC 0.85; CO₂ AUC 0.59 | CO₂ R² 0.40; helium R² −0.15 |
| More data? | Learning curve flattens after about 70% of rows | n/a |
| Physics direction | More oxygen → less extinction; more CO₂/helium and bigger droplets → more extinction | Driven mainly by droplet size, as expected |

These stress tests describe earlier full-dataset CV candidates, not the frozen burn-time pipeline or its independently calibrated intervals. Nearby tests are not a guarantee of accuracy. Predictions require physical validity, per-fuel bounds and three nearby screened sample groups of the same fuel and gas family. Methanol estimates carry a warning. See [prediction and evidence limits](PREDICTION_LIMITS.md) for the complete policy and audit method.

**Data used:** every labeled row NASA publishes for FLEX (PSI-69's 274-test table).
202 are used. 61 ended in a disruption with no clean ending, and 11 more have a
missing diameter or inconsistent gas readings (adding back the 4 recoverable
ones changes nothing meaningful: AUC 0.82 vs 0.81). The rest of NASA's FLEX/FLEX-2
archives (about 2 TB) are camera video and sensor logs with no recorded outcome;
using them would mean measuring flames from video.

Each model has a promotion gate in `train_flex.py`. If a retrain fails the gate,
the API turns that prediction off instead of showing weak numbers. The burn-time
model is a second model added after `model/model_spec.json` (which planned one);
it uses the same features, groups and leakage rules.

**Scope:** both models describe FLEX **liquid droplet** flames only. They do not
predict solid materials, ignition resistance, Moon or Mars behaviour, or
certification. The advisor ranks **evidence**, never safety.

Material comparisons accept `protocol` (`ignition_trial` or `ongoing_burn_trial`) and apply geometry/thickness consistently to tests and stages. `priority` only accepts `evidence_strength`. Event oxygen is unknown; initial oxygen is used as a proxy. Completion remains a literal NASA category. Partial-gravity behaviour is unknown in this dataset.
