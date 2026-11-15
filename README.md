# NASA Space Apps 2026 — AstraBuilders: FireSafe

FireSafe helps spacecraft engineers evaluate materials against NASA's microgravity
fire experiments (PSI: BASS, BASS-II, Saffire I-III, FLEX), or find tested candidates
from their mission conditions. The Streamlit app (`app/`) has four pages; a React web UI with a
FastAPI backend (`web/`, `api/`) is described further down.

| Page | What it does |
| --- | --- |
| **Material Advisor** (home) | *Analyze a material* or *Find a material*. Enter mission, oxygen, airflow, pressure, component shape/thickness, constraints and a priority. Each PSI-tested material gets comparable NASA tests, a model estimate, constraint checks (meets / fails / cannot assess), concerns and citations, ranked by priority and evidence strength. An AI explanation is optional. |
| **Research Assistant** | A DeepSeek-powered chat that answers from the NASA data through fixed tools (test lookup, trends, predictions, document search, advisor results), with citations, charts and research gaps. |
| **Combustion Predictor** + **Model Performance** | Sustained-burning model for solids and early-extinction model for FLEX droplets, with out-of-range warnings and grouped cross-validation metrics against baselines. |
| **NASA Data Explorer** | All 19 PSI investigations plus the NTRS ground report, the 250 solid tests, the original NASA tables, document search and Earth-gravity thresholds. |

## Run it

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export DEEPSEEK_API_KEY=...           # optional (or put it in a gitignored .env): enables the AI assistant and explanations
.venv/bin/streamlit run app/main.py
```

Without an API key everything works except the AI text: the assistant falls back to
showing the most relevant NASA passages, and the advisor shows a computed summary.

Retrain the models (rewrites `model/*.joblib` and `model/metrics.json`):
`.venv/bin/python model/train.py`. Tests: `.venv/bin/python -m unittest discover -s tests -v`.

## What the data can and cannot support

- **Solid predictor is exploratory.** 47 stages with exact conditions and a label;
  grouped-CV ROC AUC about 0.71, but a material-only model scores about as well, so
  oxygen and airflow add little so far. The FLEX droplet model (207 tests, AUC about 0.84)
  is where conditions clearly matter.
- **Labels are AI-reviewed** from crew and report notes, with no human sign-off.
- **Not covered:** partial gravity (Moon/Mars), pressures away from ~1 atm, untested
  materials, mass/cost/mechanical properties. The app flags these instead of guessing.
- **No safety certification.** Materials are only called better than one another where
  the evidence supports the comparison.

Data provenance and cleaning: [data audit and team handoff](data/DATA_HANDOFF.md),
[clean data package](data/clean/README.md), [labeling handoff](data/annotations/README.md).

## Data package, SQLite and the React/FastAPI web app

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
