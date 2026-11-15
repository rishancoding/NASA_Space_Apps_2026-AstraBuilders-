# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

NASA Space Apps 2026 (team AstraBuilders). A curated, verified package of NASA PSI (Physical Sciences Informatics) microgravity combustion data and its build pipeline (`data/`), with two front ends that share it:

- **Streamlit app** (`app/`, backend `firesafe/`, models `model/train.py` → `model/*.joblib` + `model/metrics.json`): Material Advisor, DeepSeek research assistant, combustion predictor + model card, data explorer.
- **React web UI + FastAPI** (`web/`, `api/`, models `model/train_flex.py` → `model/artifacts/`): two trained FLEX droplet models and a chat agent. See `docs/API.md`. There are no safety rankings: the advisor ranks evidence.

## Backend and models (React/FastAPI)

- `model/train_flex.py` trains the extinction classifier with grouped CV and the burn-time regressor with disjoint fitting, calibration and audit groups and writes `model/artifacts/` (joblib files with sklearn built-ins only, `metrics.json`, `oof_predictions.json`). See `docs/PREDICTION_LIMITS.md` for conditional controls, same-family support checks and the interval audit. Each model has a promotion gate; a failed gate disables that prediction in the API. The extinction model is unweighted on purpose so its probabilities stay calibrated (balanced weights gave a Brier score worse than the base rate). `model/evaluate_models.py` runs the stress tests into `evaluation.json`; rerun it after retraining.
- `api/core.py` holds every function (options, explorer, similarity, advisor, predictions, what-if, search). Numbers go through `val()` with a trust label. `api/main.py` exposes them over HTTP; `api/agent.py` gives the same functions to a language model as tools: DeepSeek (`deepseek-flash`, OpenAI-compatible SDK, `DEEPSEEK_API_KEY`) by default, or Claude (`ANTHROPIC_API_KEY`); both loops share `TOOLS`, `run_tool` and the system prompt.
- Run: `.venv/Scripts/python -m uvicorn api.main:app --reload --port 8000`. Test: `.venv/Scripts/python -m pytest api/tests -q`.

`data/DATA_HANDOFF.md` is the authoritative description of the data: what was corrected, what each teammate should use, and what must not be claimed. Read it before you change data semantics.

## Commands

Run everything from the repository root.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # app deps
.venv/bin/streamlit run app/main.py                                  # the app; DEEPSEEK_API_KEY (env or gitignored .env) enables AI text
.venv/bin/python model/train.py                                      # retrain; rewrites model/*.joblib + metrics.json
.venv/bin/python -c "from firesafe import db; db.build()"           # force-rebuild data/firesafe.sqlite (normally automatic)
sqlite3 -readonly data/firesafe.sqlite                               # inspect it; _tables/_columns hold provenance
.venv/bin/python -m unittest discover -s tests -v                    # app/backend tests (no network, no key)
.venv/bin/python -m unittest tests.test_firesafe.AdvisorTests        # one class
```

Data package (needs the extra build deps):

```sh
.venv/bin/python -m pip install -r data/requirements.txt   # openpyxl, pypdf, pdfplumber (build only)
.venv/bin/python data/scripts/fetch_sources.py             # network + curl; caches into data/raw/ (gitignored)
.venv/bin/python data/scripts/build_data.py                # offline; regenerates data/clean/ (label files come out blank)
.venv/bin/python data/scripts/label_data.py                # offline; applies data/annotations/ -> labeled/training CSVs
.venv/bin/python -m unittest discover -s data/tests -v     # all tests
.venv/bin/python -m unittest data.tests.test_data.DataTests.test_units_and_zero   # single test
.venv/bin/python -m unittest discover -s data/tests -p 'test_labels.py' -v      # label checks only; no openpyxl needed
```

- `python data/scripts/build_sqlite.py` builds `data/flame.sqlite` from `data/clean/` (one table per CSV, `src_*` for NASA source tables, `_tables`/`_columns` catalogue). Rerun it after `build_data.py` or `label_data.py`; `data/tests/test_sqlite.py` checks every cell.
- `data/clean/cleaning_pipeline.py` is a legacy shim that forwards to `build_data.py`.
- `data/tests/test_data.py` imports `build_data`, so it needs `data/requirements.txt` installed (otherwise it errors with `No module named 'openpyxl'`); `tests/` needs only `requirements.txt`. They do not need `data/raw/`. The raw-vs-clean comparisons are skipped when the cache is missing.
- To read the committed `data/clean/` files you need only the standard library (`data/access.py`).
- Don't delete `data/raw/` just to rerun the build. Cached metadata pins the source versions, and the build verifies the SHA-256 checksums recorded in `source_manifest.json`. To pull new NASA versions, use a separate raw cache and review the diff.

## Architecture

The pipeline runs in one direction: **fetch → build → label → clean package → train/readers**. After `build_data.py`, always run `label_data.py` (and then `model/train.py` if training data changed): the build rewrites `label_review_queue.csv` unlabeled.

- `data/scripts/fetch_sources.py` defines `RECORDS` (the 19 PSI accessions) plus `ROOT`/`RAW`. It downloads metadata, the selected experimental tables, readmes and reports from NASA's public PSI endpoints, plus the external NTRS report.
- `data/scripts/build_data.py` writes every file in `data/clean/`, and every file there is generated. It reconciles BASS (PSI-26) against its as-run workbook, merges BASS-II (PSI-25) with Appendix A observations from its report PDF, builds the FLEX (PSI-69) droplet backup, exports the source tables unchanged, chunks document text into `evidence_chunks.jsonl`, and writes the quality report, data contract and manifest. If joins or CSV structures don't reconcile, the build fails rather than guessing.
- `data/scripts/ground_reference.py` holds a hand transcription of the NTRS 20110008636 ULOI/MOC tables, with table/page provenance on each row (`ground_thresholds.csv`).
- `data/access.py` provides the dependency-free readers (`query_experiments`, `load_catalog`, `load_source_tables`, `load_evidence`, `load_quality_report`, `load_training_candidates`) that the dashboard, agent and model code use. `query_experiments` validates filter names and converts numeric blanks to `None`.
- Join key across catalog, observations, evidence and tables: `source_record` (e.g. `PSI-25`). `table_index.json` maps each source table to its file, original headers, encoding and row count.
- `data/scripts/label_data.py` applies `data/annotations/solid_test_reviews.jsonl` and `solid_stage_reviews.jsonl` (team-verified reviews keyed by experiment ID) to produce `solid_combustion_model.csv`, `solid_stage_*.csv`, `flex_labeled.csv`, `flex_training.csv`, `label_review_queue.csv` and `labeling_report.json`. Those JSONL files are the editable inputs; don't hand-edit the generated CSVs. Each review hashes its source note and conditions, so the labeler fails if those fields change after review.

App layers (all numbers come from the backend, never the LLM):

- `firesafe/data.py` loads `data/clean/` CSVs into cached DataFrames (the "database"), plus a hand-transcribed `SAFFIRE` list (blank-material rows stay unattributed). `firesafe/evidence.py` is BM25 search over `evidence_chunks.jsonl`.
- `firesafe/predictor.py` trains/serves two models: solid sustained burning (logistic regression on material + scenario/`protocol` + oxygen + log-airflow terms, leave-one-group-out CV) and FLEX droplet extinction (best of LR/RF by grouped-CV log loss). Feature helpers live in this module so the joblib files load anywhere. `predict_solid` returns warnings for every out-of-range input (oxygen, airflow, untested scenario, pressure, gravity).
- `firesafe/advisor.py` matches a `Scenario` to tests (±1.5 pp O2, ±50% airflow), computes evidence strength, constraint checks (`meets`/`fails`/`cannot assess`/`outside data`), ranks by priority with evidence tier first, and marks pairwise comparisons `supported` only when the evidence allows. The selected material in analyze mode is kept out of the ranking.
- `firesafe/db.py` builds `data/firesafe.sqlite` (gitignored) from `data/clean/`: the curated CSVs under their file stems, `saffire_samples` from the `SAFFIRE` list, and every original NASA table as `src_*` (all TEXT, verbatim, `_source_row` = CSV line, which joins to curated `source_row`). Blank cells become NULL. `_tables`/`_columns` hold source file, grain, caveats, investigations and units. `ensure()` rebuilds when the fingerprint (input files + `db.py` source) changes. `run_select` is the only query path: read-only URI, `query_only`, an authorizer that permits SELECT/READ/FUNCTION only, a VM-step limit and a 200-row cap. Investigations come from `source_record`, or the `experiment_id` prefix (`PSI-25:...`).
- `firesafe/reliability.py` turns `model/metrics.json` out-of-fold data into a review for each prediction: model statistics against the constant baseline and the simpler (material-only/fuel-only) model, plus five checks (inputs in range, beats baseline by 10% log loss, conditions add skill, at least 10 training rows, local calibration). Those give a `low`/`moderate`/`higher` rating; the solid model is capped at `moderate`.
- `firesafe/tools.py` is the agent's read-only tool set (`TOOLS` schemas + `run_tool`, which rejects unknown arguments). It includes curated lookups, `query_database`/`describe_database` (SQL via `db.run_select`) and predictions (`predict_*`, `prediction_sweep`). Each prediction carries a `reliability` review. `run_tool` puts a `provenance` block (datasets, investigations, model files, documents, SQL) first in every result; when you add a tool, add it to `TOOL_DATASETS`. `firesafe/agent.py` builds the system prompt (`SYSTEM_RULES` + `db.schema_text()`), which requires **Prediction reliability** and **Sources** sections, and runs a manual tool loop on DeepSeek `deepseek-v4-pro` through the `anthropic` SDK pointed at DeepSeek's Anthropic-compatible endpoint (`https://api.deepseek.com/anthropic`; override with `FIRESAFE_MODEL` / `FIRESAFE_BASE_URL`) via `client.messages.create`; assistant content (including DeepSeek `thinking` blocks) is appended back unchanged. `offline_answer` is the no-key fallback.
- `app/main.py` uses `st.navigation`; pages are in `app/pages/`, shared charts in `app/ui.py`. The advisor stores its result in `st.session_state.advisor_result`, which the assistant reads through `get_current_advisor_results`.
- `data/annotations/` holds project-team-verified labels. Rebuilds overwrite `data/clean/`, so copy `label_review_queue.csv` here before you edit it.

## Data invariants (enforced by tests or required by the handoff)

- A numeric blank means missing, never zero. A single numeric zero airflow is kept as zero.
- Source tables keep NASA's original cell values, headers, note/calibration rows and typos. Don't "fix" them.
- `airflow_raw` keeps lists, ranges, inequalities and verbal flow descriptions. Don't average them or reduce them to a single number. BASS-II `Fan display` is not airspeed; `Air display` is airspeed in cm/s.
- BASS oxygen in the workbook is a fraction (0.221 means 22.1%). BASS-II oxygen is already a percent. Pressure is converted from atm at 101.325 kPa/atm. Don't invent a default pressure for BASS-II.
- Thickness, width and diameter are separate fields. A rod diameter is never thickness.
- Labels come from `data/scripts/label_data.py` plus the team-verified annotations in `data/annotations/*.jsonl`. In `solid_combustion_model.csv`, `burned_binary` means "any flame observed" (226 yes / 6 no / 18 blank) and `training_eligible` is false for every test, so it is not a training target. The solid training set is `solid_stage_training.csv` (47 stages, `sustained_flame_binary`, grouped by `validation_group`); the FLEX one is `flex_training.csv`. Extinction after a burn, hardware failure and fuel exhaustion are not "did not burn".
- The solid model is exploratory: a material-only model scores about as well as the deployed one. Keep that comparison (and the constant baseline) visible on the model page; don't tune features to make the sliders look responsive.
- Uniqueness: BASS needs date + as-run number + test number + sample number. FLEX's experiment key includes the test number, because `193F001` repeats. Use `split_group` to keep repeat burns of one sample together in validation.
- Evidence chunks of kind `experiment_plan_text` describe proposed tests and must not be cited as observed outcomes. Ground thresholds are Earth-gravity, external to PSI, and are not training outcomes.
- Never present a ranking as a safety certification, or claim one material is safer unless the advisor's comparison is `supported`. Partial gravity, pressures away from ~1 atm, mass, cost and mechanical properties are always "cannot assess".
- Don't present safety rankings or extrapolations in the app or agent. Model numbers appear only when the model passed its gate and the input is inside the tested range; the FLEX models describe droplets, never solid materials.

## Git

Commit `firesafe/`, `app/`, `model/` (including the joblib files and metrics), `tests/`, `data/clean/`, `data/scripts/`, `data/access.py`, `data/tests/`, requirements and docs. `data/raw/` (downloads, media, archives) and the generated `data/firesafe.sqlite` stay local.
