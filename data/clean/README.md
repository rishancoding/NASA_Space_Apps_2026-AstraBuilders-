# Curated NASA combustion data

These are real NASA records, rebuilt from selected tables and documents. See
[the handoff guide](../DATA_HANDOFF.md) before using them in the app or a model.

| File | Contents | Later consumer |
| --- | --- | --- |
| `solid_combustion_model.csv` | 250 BASS/BASS-II test observations, with conditions, crew notes and provenance | Model preparation, experiment lookup, advisor |
| `label_review_queue.csv` | Completed project team verification of 250 tests, with unresolved outcomes retained | Model lead and evidence audit |
| `solid_stage_observations.csv` | Condition-linked events and explicit exclusions | Model preparation and agent |
| `solid_stage_training.csv` | 47 conservative labeled stage candidates | Exploratory solid-fuel model |
| `airflow_readings.csv` | Ordered display readings; no assumed outcome alignment | Evidence review |
| `flex_labeled.csv` / `flex_training.csv` | All FLEX labels / 202 physically screened extinction-versus-completion candidates | Selected exploratory model |
| `labeling_report.json` | Review coverage, class balance, exclusions and feature whitelists | Model lead |
| `model_readiness.json` | Step 2 coverage audit, exclusions and model selection rationale | Model lead |
| `investigation_catalog.csv` | All 19 requested PSI investigations plus the external NTRS report | Explorer and research assistant |
| `source_tables/` | All 21 selected NASA experimental CSV tables, plus BASS science rows, BASS-II report observations and calibration cells | Evidence, comparisons, numerical lookups |
| `table_index.json` | Table locations, original headers, encodings, row counts and versions | Shared ingestion code |
| `evidence_chunks.jsonl` | NASA metadata and scientific document/report text with locators | Retrieval for the research assistant |
| `publications.csv` | Publication metadata and DOI/source links from PSI | Citations and follow-up research |
| `flex_backup.csv` | 274 liquid-droplet observations | Separate fallback model preparation |
| `ground_thresholds.csv` | 70 Earth-gravity ULOI/MOC threshold pairs from Tables 2–9 | Ground comparison only |
| `quality_report.json` | Missing values, flagged data, coverage and model readiness | All consumers |
| `data_contract.json` | Field types, units, null handling, identifiers and joins | All consumers |
| `source_manifest.json` | NASA download endpoints, versions and SHA-256 checksums | Reproduction and provenance |
| `excluded_rows.csv` | One excluded soot-cleaning operation | Audit |

`solid_combustion_model.csv` retains its original filename for compatibility.
It is a **whole-test observation table**. `burned_binary` now records any visible
flame reported anywhere in a test, including brief ignition. Whole-test rows stay
ineligible for condition-specific training; use the separate stage candidates.
All 250 tests have team-verified review records, with 18 any-flame labels still unresolved.
See the [labeling handoff](../annotations/README.md) for target definitions and
limitations. No predictions, trained model or validation metrics are included.

All numeric CSV blanks mean missing/unsupported, never zero. Source CSVs retain
NASA's original values, headers, note rows, approximations and apparent typos.
The raw files, media and large archives are excluded from Git.
