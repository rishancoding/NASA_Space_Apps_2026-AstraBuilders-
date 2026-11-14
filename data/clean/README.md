# Curated NASA combustion data

These are real NASA records, rebuilt from selected tables and documents. See
[the handoff guide](../DATA_HANDOFF.md) before using them in the app or a model.

| File | Contents | Later consumer |
| --- | --- | --- |
| `solid_combustion_model.csv` | 250 BASS/BASS-II test observations, with conditions, crew notes and provenance | Model preparation, experiment lookup, advisor |
| `label_review_queue.csv` | 250 tests with evidence and blank annotation fields | Model lead; copy before editing |
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
It is an **observation table, not a labeled training set**. `burned_binary` is
blank, `training_eligible` is false, and every test needs target/condition review.
No video-derived labels, invented measurements, predictions or metrics are included.

All numeric CSV blanks mean missing/unsupported, never zero. Source CSVs retain
NASA's original values, headers, note rows, approximations and apparent typos.
The raw files, media and large archives are excluded from Git.
