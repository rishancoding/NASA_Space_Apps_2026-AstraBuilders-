# NASA Space Apps 2026 — AstraBuilders: FireSafe

FireSafe helps spacecraft engineers evaluate materials against NASA's microgravity
fire experiments (PSI: BASS, BASS-II, Saffire I-III, FLEX), or find tested candidates
from their mission conditions. It has four pages:

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
