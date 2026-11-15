# ThermaGuard — AstraBuilders

*Fire behaviour insights from NASA microgravity research.*

**The official project and submission app is React + FastAPI (`web/` + `api/`).**
It explores NASA microgravity combustion evidence and estimates FLEX liquid-droplet outcomes only where comparable screened tests exist.

| Workspace | What you can do |
| --- | --- |
| Material Advisor | Compare nearby NASA observations by material, geometry and trial protocol. Use the fixed closeness-weighted evidence order, with its explanation shown above results; it is not a safety ranking. |
| Atmosphere Predictor | Start from a real NASA FLEX test and adjust supported nearby settings. View Extinction probabilities and independently calibrated burn-time intervals. |
| NASA Data Explorer | Browse investigations and experiments, compare tests, inspect sources and search NASA report passages. |
| Model Accuracy | Inspect grouped validation, calibration, independent burn-time audit results and limitations. |
| Research assistant | Ask a configured DeepSeek/Claude model to call the same data tools. Without a provider key the data workspaces and API tools still work. |

## Run the official app

Use Python 3.11+ and Node.js 22.12+.

From the repository root, first-time backend setup on macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements.txt
.venv/bin/python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd web
npm ci
npm run dev -- --host 127.0.0.1
```

- UI: http://127.0.0.1:5173
- Interactive API tools: http://127.0.0.1:8000/docs
- Backend status: http://127.0.0.1:8000/api/health

On Windows, use `python` instead of `python3` and `.venv/Scripts/python` instead of `.venv/bin/python`.

For optional AI chat, copy `.env.example` to `.env` without overwriting an existing file, add a provider key privately and restart the API. See [collaborator setup](docs/COLLABORATOR_SETUP.md). Never place a key in `web/` or a `VITE_` variable. A configured key is not proof that a provider call succeeds.

For a frontend production build: `cd web && npm ci && npm run build`. Set `VITE_API_URL` to the public backend address before building when deploying to separate hosts. This repository's local preview is not a public deployment.

## Data and model scope

- 19 NASA PSI investigations plus an external NASA ground-test report.
- 250 BASS/BASS-II solid tests; 274 raw FLEX droplet observations; **202 screened FLEX training rows** (176 Extinction, 26 Completion).
- Solid outcomes are derived annotations verified by the project team, not NASA certification. Initial oxygen is a proxy for event conditions. Ignition and already-burning events are counted separately.
- The official app does **not** deploy a solid-material burn classifier or rank materials by safety.
- The official FLEX extinction classifier is logistic regression with interactions: grouped-CV balanced accuracy approximately 0.804, ROC AUC approximately 0.88 and Brier score approximately 0.076. These are exploratory internal validation results, not guarantees at every condition.
- The burn-time model has 119 fitting rows, 41 calibration rows and 40 independent audit rows. Audit R² is approximately 0.612, MAE 2.90 seconds, and its nominal 90% interval covered 36 of 40 audit groups.
- Invalid mixtures, out-of-range inputs and combinations with fewer than three nearby screened sample groups produce no prediction. The controls follow the same checks.
- Completion remains NASA's recorded category; it is not expanded into an unsupported physical endpoint. Moon/Mars behaviour is unknown in this dataset.

[Prediction limits and interval method](docs/PREDICTION_LIMITS.md) · [NASA data handoff](data/DATA_HANDOFF.md) · [Label provenance](data/annotations/README.md) · [AI assistance disclosure](docs/AI_USE.md)

## Database and checks

Rebuild the packaged SQLite database after data or label changes:

```sh
python3 data/scripts/build_sqlite.py
```

`data/flame.sqlite` contains the curated tables, verbatim NASA source tables, evidence passages and provenance catalogues. The official API reads the cleaned package directly. Missing numeric values remain missing.

With API and data build dependencies installed:

```sh
python3 -m pytest api/tests model/tests data/tests -q
```

The model files and their corresponding metrics live in `model/artifacts/`. `model/train_flex.py` rebuilds the official models; `--task burn-time` rebuilds only the independently calibrated burn-time model. Historical candidate stress tests are labeled separately from its independent audit.

## Experimental reference app

`app/`, `firesafe/`, `model/train.py`, and `model/*.joblib` are the separate Streamlit reference implementation. **They are not the submission entry point.** Its historical classifiers and scores differ from the official models. It shares the official FLEX physical/range/coverage checks; unsupported probabilities are withheld in its UI and tools too. Its solid classifier remains experimental and is not used by the official Material Advisor.

To maintain that reference app only, install `requirements.txt` and run `python -m streamlit run app/main.py`. Its tests additionally need those requirements: `python -m pytest tests -q`.
