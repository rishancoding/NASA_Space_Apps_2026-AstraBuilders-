# Flame in Freefall — web UI

React + Vite + Tailwind + Recharts. It talks only to the FastAPI backend in `../api`
(see `../docs/API.md`).

## Run

```sh
# terminal 1, from the repo root: the API
.venv/Scripts/python -m uvicorn api.main:app --reload --port 8000

# terminal 2: the UI
cd web
npm install
npm run dev          # http://localhost:5173 (calls to /api are proxied to port 8000)
```

For chat, copy the repository-root `.env.example` to `.env` and add the DeepSeek
key you receive privately from the project owner. The backend loads it on startup;
restart the API after editing it. Existing terminal environment variables take
precedence. Keep API keys out of `web/` and all `VITE_` variables, which are exposed
in browser builds. See [collaborator setup](../docs/COLLABORATOR_SETUP.md).
For a deployed build, set `VITE_API_URL` to the API's public address, then `npm run build`.

## Layout

| File | What it is |
| --- | --- |
| `src/api.js` | One function per backend endpoint; errors come back as `ApiError.errors` = `[{field, message}]` |
| `src/components/ui.jsx` | Shared pieces: `Value` (renders `{value, unit, trust, range}`), `TrustBadge`, `Slider`, `Card`, `useAsync`, `useDebounced` |
| `src/App.jsx` | Header, page switching (`#advisor`, `#predictor`, `#explorer`, `#model`), chat and detail drawer |
| `src/pages/Advisor.jsx` | Material Advisor: analyze / find modes, presets, ranked evidence cards |
| `src/pages/Predictor.jsx` | Atmosphere Predictor: sliders, both model results, what-if chart, drivers, nearest tests |
| `src/pages/Explorer.jsx` | Investigations, test table with filters and compare, report search |
| `src/pages/ModelPage.jsx` | Accuracy: headline metrics, calibration chart, predicted-vs-actual, stress tests |
| `src/components/ChatPanel.jsx` | Research-assistant chat with citations and "looked up" tool list |
| `src/components/ExperimentDrawer.jsx` | Full detail for one NASA test |

Every form is built from `GET /api/options`, so slider ranges and dropdowns update when the data does.

## Supported controls and validation

The predictor starts from a screened NASA test. Fuel and gas-mixture switches reset all inputs, and sliders use conditional settings returned by `/api/predict/controls`. Fixed zero gas components are shown in the composition summary. The backend also rejects unsupported combinations, including what-if curve points. See [prediction limits](../docs/PREDICTION_LIMITS.md).

The Material Advisor separates ignition and already-burning events and labels initial oxygen as a proxy. The Model Accuracy page shows independent burn-time audit results separately from historical CV stress tests. The UI has responsive navigation, visible focus indicators, reduced-motion support, loading/error states and lazy-loaded pages.

Checks: `npm ci && npm run build`; from the repository root, `python3 -m pytest api/tests model/tests -q` (with API requirements installed). Data/SQLite checks remain `python3 -m unittest discover -s data/tests` (with build requirements installed).
