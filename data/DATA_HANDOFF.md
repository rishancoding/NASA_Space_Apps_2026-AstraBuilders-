# NASA data audit and team handoff

The previous package contained **zero experiment rows**, a 7-source catalog and
a generic CSV renamer. It had not downloaded or cleaned the NASA files. This
package replaces those placeholders with verified NASA data from the complete
source list in the supplied plan.

## Verified coverage

| Intended use | Sources | Included |
| --- | --- | --- |
| Solid observations | PSI-26 BASS; PSI-25 BASS-II | 121 + 129 tests, source CSVs, BASS as-run conditions/notes, BASS-II matrices/readme/calibration and report text |
| Large-fire evidence | PSI-98 Saffire-I; PSI-99 Saffire-II; PSI-100 Saffire-III | All three experimental tables, objectives, approaches, readmes where available and research references |
| Droplet fallback | PSI-69 FLEX | 274 observations, original table, data-organization document and test-plan text |
| Research assistant | PSI-68 FLEX-2; PSI-39 CFI; PSI-10 Flame Design; PSI-20 BRE; PSI-21 CLD Flame; PSI-22 E-FIELD Flames; PSI-23 s-Flame; PSI-159 CFI-G; PSI-107 SPICE; PSI-106 SLICE; PSI-102 SAME; PSI-101 SAME-R; PSI-47 DAFT/DAFT-2 | Verified NASA metadata, all selected experimental tables and publication metadata |
| External ground comparison | NTRS 20110008636, *Selected Parametric Effects on Materials Flammability Limits* | Report text with PDF page locators; 70 reported ULOI/MOC pairs from Tables 2–9 |

The 19 PSI records match the requested investigations. The catalog contains 20
sources including NTRS. `table_index.json` indexes 21 NASA experimental tables
with 2,862 rows, including NASA's note/calibration rows. These are not 2,862
interchangeable training tests. Additional science extracts are stored beside
the source tables. No subsampling was used.

Scope is the selected experimental tables and the documents necessary to
interpret them, plus investigation metadata/publication references for the
research sources. Full telemetry, every publication's full text, videos,
photos, image proof sheets and bulk archives are outside this curated package.
The pasted plan was the only supplied attachment; no additional uploaded data
files were present in the workspace.

## What was corrected

- BASS has 122 source-table rows; one is a soot-cleaning operation. All 121
  material tests are retained and reconciled to the as-run workbook using date,
  as-run number, test number and sample number. Neither test number nor as-run
  number alone is unique. Duplicate year-specific workbook tabs are not stacked.
- BASS crew observations, oxygen, pressure and flow settings were recovered
  from the as-run workbook. Oxygen is stored as a fraction despite the percent
  header: 0.221 becomes 22.1%. Pressure is converted from atm using 101.325 kPa/atm.
- BASS-II's experimental table contains 129 tests. Its 144-page NASA summary
  report supplies observations for 126 tests in Appendix A, PDF pages 111–121.
  Tests O20, O21 and O22 have no matched report observation and remain flagged.
- `Air display` is airspeed in cm/s, per BASS-II's ReadMe. `Fan display` is a
  different instrument signal and is never treated as airspeed. Lists, ranges,
  inequalities and verbal flow descriptions remain in `airflow_raw`; they are
  not averaged or reduced to the first number. Single numeric zero is retained.
- BASS-II calibrated oxygen is already percent. Final oxygen values 39.1% for
  P22b and 40.4% for T28b are retained and flagged for review, not silently fixed.
  No default pressure was invented for BASS-II.
- Nominal sheet thickness, width and rod/sphere diameter are separate fields.
  Microns and inches are converted to mm only where stated. A rod diameter is
  never used as thickness. Descriptions may refer to original sample dimensions
  even when repeated burns have reduced the actual specimen size.
- Material families are resolved from explicit descriptions, BASS-II PI sample
  definitions, or an explicit description of the same sample in the same
  investigation. Unresolved identities remain flagged. Natural/blended Nomex,
  clear/black PMMA and geometry differences remain in `material_raw`; a shared
  family name does not establish equivalent material performance.
- Source tables retain every original cell value and column, including Saffire
  notes, blank material cells and entries such as `037 mm`. They are exported
  as UTF-8 without guessing corrections. FLEX's ambiguous burning-rate header
  is retained as raw text and its unit is marked for verification.
- FLEX's source identifier `193F001` appears in two different numbered tests.
  Both are retained; the unique experiment key includes the test number. The
  shared source identifier is retained as a conservative validation group.
- The ground report does not substantiate a generic "22-material oxygen limits"
  table. The actual extraction contains 70 configuration-specific pairs across
  12 material families. ULOI and MOC are different thresholds, not training
  outcomes. Repeated values across report tables are retained with context.

## Files for each teammate

**Model lead:** Start with `clean/solid_combustion_model.csv`, the data contract
and quality report. Copy `clean/label_review_queue.csv` into `data/annotations/`
before editing; generated files are overwritten on rebuild. Define one target
and consistent observation conditions, then review notes against their source
locators. A whole test can contain multiple flow changes, re-ignitions, forced
suppression and fuel exhaustion. It cannot automatically supply one binary
label for its initial oxygen/airflow. Extinction after a real burn is not a
"did not burn" result. Hardware failure or depleted fuel is also not evidence
of intrinsic ignition resistance. All `burned_binary` cells currently remain
blank and `training_eligible` is false. The package is ready for annotation,
not for immediately fitting a burn/no-burn model.

If the selected target requires separate condition segments, create a reviewed
training table with `experiment_id`, a segment identifier, actual conditions,
target value, reviewer and source locator. Preserve the original observations.
Use `split_group` to keep repeat burns of the same sample together in validation;
review possible cross-investigation sample reuse too. Do not use final gas
measurements, crew prose, IDs or source-specific camera settings as predictive
features. Record labels, feature choices, sample exclusions and validation
metrics in the later model commit. FLEX remains a separate fallback dataset.

**Dashboard/advisor lead:** Read the observation table for actual experiments,
the source tables for Saffire evidence, and the catalog for source cards. Offer
tested material families and variants. A numeric range in the observed data is
not a validated model range. Do not present safety rankings, model probabilities,
mass/strength/budget checks or pressure extrapolations before the corresponding
backend/model evidence exists.

**Agent lead:** Index `clean/evidence_chunks.jsonl`. Each chunk has a stable
`chunk_id`, `source_record`, `source_file`, `locator`, `kind`, `source_url` and
text. Metadata, reports, experiment plans and readmes are distinct kinds. Plans
describe proposed tests and must not be cited as observed outcomes. This is extracted text,
not an LLM-authored scientific conclusion; PDF layout may flatten tables. Use
structured source tables for calculations, and cite the actual record plus the
file/page or test locator. `publications.csv` contains references, not the full
text of all listed papers. Retrieve a small selection per answer.

**Explorer lead:** `investigation_catalog.csv` joins to observations, evidence
and tables by `source_record`. `table_index.json` lists the original measured
variables, schema and row counts for each source table. NASA DOI and license
metadata are included. Ground evidence is explicitly external to PSI.

The dependency-free readers in `data/access.py` support those integrations:

```python
from data.access import query_experiments, load_catalog, load_source_tables, load_evidence

pmma_tests = query_experiments(material="PMMA", source_record="PSI-25")
saffire = load_source_tables("PSI-99")
research = load_evidence("PSI-26")
```

Numeric observation blanks become `None`; original table values remain strings.
Filter names are validated. These readers perform no model predictions/ranking.

## Rebuild and verify

Run from the repository root. Consuming the committed clean files needs only
Python's standard library. Rebuilding needs Python 3.10+ and the pinned readers:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r data/requirements.txt
.venv/bin/python data/scripts/fetch_sources.py
.venv/bin/python data/scripts/build_data.py
.venv/bin/python -m unittest discover -s data/tests -v
```

The old command `python3 data/clean/cleaning_pipeline.py` forwards to the same
builder. Fetching uses NASA's public PSI metadata/download endpoints and caches
source versions. Building runs offline, verifies downloaded source checksums
and fails if BASS joins or CSV structures do not reconcile. The source manifest
records SHA-256 hashes, versions and permanent download endpoint parameters;
temporary signed download URLs are not stored. Ground transcription lives in
`scripts/ground_reference.py`, with table/page provenance on every output row.

Commit `data/clean/`, `data/scripts/`, `data/access.py`, `data/tests/`, requirements
and documentation. `data/raw/` stays local and is ignored.
