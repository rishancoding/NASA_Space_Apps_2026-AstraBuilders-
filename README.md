# NASA Space Apps 2026 — AstraBuilders

Curated NASA PSI combustion data for the material advisor, research assistant,
data explorer and later model development.

Start with the [data audit and team handoff](data/DATA_HANDOFF.md). The
[clean data package](data/clean/README.md) includes 250 solid-fuel observations,
274 FLEX droplet observations, all 19 requested PSI investigations and the
external ground-test comparison. Evidence-linked AI labels and conservative
training candidates are included; see [the labeling handoff](data/annotations/README.md).
No trained predictor or validated safety rankings are included yet.

Steps 1–2 are documented in the [competition requirements review](docs/COMPETITION_REQUIREMENTS.md)
and [model scope](docs/MODEL_SCOPE.md). The selected exploratory model uses 202
screened FLEX observations; solid-material comparisons remain evidence-based.

**SQLite database:** `python data/scripts/build_sqlite.py` builds `data/flame.sqlite`
from the cleaned files (standard library only, a few seconds). It has one table per
CSV in `data/clean/` (typed columns), one `src_*` table per NASA source table
(original text), `evidence_chunks`, and two catalogue tables: `_tables` (what each
table is, its source file and row count) and `_columns` (original header → column
name and type). Blank cells are `NULL`, never 0. Check it with
`python -m unittest data.tests.test_sqlite`.

```sql
SELECT material, COUNT(*) FROM solid_combustion_model GROUP BY material;
SELECT * FROM _tables;   -- start here
```

**Backend for the UI:** a FastAPI app (`api/`) with the material advisor, FLEX
extinction and burn-time models (`model/`), what-if curves, similarity search,
NASA text search and a research-assistant agent (DeepSeek or Claude). Start with the
[API guide](docs/API.md):

```sh
.venv/Scripts/python -m pip install -r api/requirements.txt
.venv/Scripts/python -m uvicorn api.main:app --reload --port 8000   # then open http://localhost:8000/docs
```

For local chat, copy `.env.example` to `.env` and add a DeepSeek key shared privately
by the project owner. The backend loads this file automatically; it is ignored by
Git. See [collaborator setup](docs/COLLABORATOR_SETUP.md) for Windows/macOS/Linux
instructions and the distinction between repository access and secret access.
