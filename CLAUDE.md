# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

NASA Space Apps 2026 (team AstraBuilders). Curated NASA PSI (Physical Sciences Informatics) microgravity combustion data that later feeds a material advisor, a research-assistant agent, a data explorer and model development. Right now the repo holds a verified data package and its reproducible build pipeline. No trained model, predictions or safety rankings exist yet. `agent_querying/` (`build_database.py`, `query_functions.py`) holds empty placeholders for the upcoming agent work.

`data/DATA_HANDOFF.md` is the authoritative description of the data: what was corrected, what each teammate should use, and what must not be claimed. Read it before you change data semantics.

## Commands

Run everything from the repository root.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r data/requirements.txt   # openpyxl, pypdf, pdfplumber (build only)
.venv/bin/python data/scripts/fetch_sources.py             # network + curl; caches into data/raw/ (gitignored)
.venv/bin/python data/scripts/build_data.py                # offline; regenerates data/clean/
.venv/bin/python -m unittest discover -s data/tests -v     # all tests
.venv/bin/python -m unittest data.tests.test_data.DataTests.test_units_and_zero   # single test
```

- `data/clean/cleaning_pipeline.py` is a legacy shim that forwards to `build_data.py`.
- The tests import `build_data`, so they need the venv dependencies. They do not need `data/raw/`. The raw-vs-clean comparisons are skipped when the cache is missing.
- To read the committed `data/clean/` files you need only the standard library (`data/access.py`).
- Don't delete `data/raw/` just to rerun the build. Cached metadata pins the source versions, and the build verifies the SHA-256 checksums recorded in `source_manifest.json`. To pull new NASA versions, use a separate raw cache and review the diff.

## Architecture

The pipeline runs in one direction: **fetch → build → clean package → readers**.

- `data/scripts/fetch_sources.py` defines `RECORDS` (the 19 PSI accessions) plus `ROOT`/`RAW`. It downloads metadata, the selected experimental tables, readmes and reports from NASA's public PSI endpoints, plus the external NTRS report.
- `data/scripts/build_data.py` writes every file in `data/clean/`, and every file there is generated. It reconciles BASS (PSI-26) against its as-run workbook, merges BASS-II (PSI-25) with Appendix A observations from its report PDF, builds the FLEX (PSI-69) droplet backup, exports the source tables unchanged, chunks document text into `evidence_chunks.jsonl`, and writes the quality report, data contract and manifest. If joins or CSV structures don't reconcile, the build fails rather than guessing.
- `data/scripts/ground_reference.py` holds a hand transcription of the NTRS 20110008636 ULOI/MOC tables, with table/page provenance on each row (`ground_thresholds.csv`).
- `data/access.py` provides the dependency-free readers (`query_experiments`, `load_catalog`, `load_source_tables`, `load_evidence`, `load_quality_report`) that the dashboard, agent and model code use. `query_experiments` validates filter names and converts numeric blanks to `None`.
- Join key across catalog, observations, evidence and tables: `source_record` (e.g. `PSI-25`). `table_index.json` maps each source table to its file, original headers, encoding and row count.
- `data/annotations/` holds the human-reviewed labels. Rebuilds overwrite `data/clean/`, so copy `label_review_queue.csv` here before you edit it.

## Data invariants (enforced by tests or required by the handoff)

- A numeric blank means missing, never zero. A single numeric zero airflow is kept as zero.
- Source tables keep NASA's original cell values, headers, note/calibration rows and typos. Don't "fix" them.
- `airflow_raw` keeps lists, ranges, inequalities and verbal flow descriptions. Don't average them or reduce them to a single number. BASS-II `Fan display` is not airspeed; `Air display` is airspeed in cm/s.
- BASS oxygen in the workbook is a fraction (0.221 means 22.1%). BASS-II oxygen is already a percent. Pressure is converted from atm at 101.325 kPa/atm. Don't invent a default pressure for BASS-II.
- Thickness, width and diameter are separate fields. A rod diameter is never thickness.
- Labels come from `data/scripts/label_data.py` plus the AI-reviewed annotations in `data/annotations/*.jsonl` (no human sign-off). In `solid_combustion_model.csv`, `burned_binary` means "any flame observed" (226 yes / 6 no / 18 blank) and `training_eligible` is false for every test, so it is not a training target. The solid training set is `solid_stage_training.csv` (47 stages, `sustained_flame_binary`, grouped by `validation_group`); the FLEX one is `flex_training.csv`. Extinction after a burn, hardware failure and fuel exhaustion are not "did not burn".
- `burn_model.joblib` is a scikit-learn logistic-regression pipeline. Its training code isn't in the repo, and loading it needs a function named `airflow_ushape` defined in `__main__`.
- Uniqueness: BASS needs date + as-run number + test number + sample number. FLEX's experiment key includes the test number, because `193F001` repeats. Use `split_group` to keep repeat burns of one sample together in validation.
- Evidence chunks of kind `experiment_plan_text` describe proposed tests and must not be cited as observed outcomes. Ground thresholds are Earth-gravity, external to PSI, and are not training outcomes.
- Don't present safety rankings, model probabilities or extrapolations in the app or agent until model evidence exists.

## Git

Commit `data/clean/`, `data/scripts/`, `data/access.py`, `data/tests/`, requirements and docs. `data/raw/` (downloads, media, archives) stays local.
