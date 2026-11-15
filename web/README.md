# ThermaGuard — web UI

**Official submission frontend.** React + Vite + Tailwind + Recharts. It talks only to the FastAPI backend in `../api`
(see `../docs/API.md`).

## Run

```sh
# terminal 1, from the repo root: the API
.venv/bin/python -m uvicorn api.main:app --reload --port 8000

# terminal 2: the UI
cd web
npm ci
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

The predictor automatically chooses supported starting conditions near the requested fuel/mixture settings, without a NASA-test selector. Fuel and gas-mixture switches reset all inputs to a supported scenario, and sliders use conditional settings returned by `/api/predict/controls`. Fixed zero gas components are shown in the composition summary. The backend also rejects unsupported combinations, including what-if curve points. See [prediction limits](../docs/PREDICTION_LIMITS.md).

The Material Advisor separates ignition and already-burning events and labels initial oxygen as a proxy. The Model Accuracy page shows independent burn-time audit results separately from historical CV stress tests. The UI has responsive navigation, visible focus indicators, reduced-motion support, loading/error states and lazy-loaded pages.

Checks: `npm ci && npm run build`; from the repository root, `python3 -m pytest api/tests model/tests -q` (with API requirements installed). Data/SQLite checks remain `python3 -m unittest discover -s data/tests` (with build requirements installed).

## Guided home and result requests

The default route is Home (`#home`), with explanations and links to all four workspaces, and the assistant. Material and atmosphere workspaces start without results. Set conditions and select **View observations** or **Generate estimates**. Editing conditions hides the old results until another submission. Conditional predictor-control checks still run to keep settings within supported coverage; they do not generate forecasts.

Material cards lead with sustained/not-sustained event counts for the selected trial protocol, with the reviewed-event denominator and initial-oxygen limitations. Whole-test totals and outcomes remain supporting context rather than being combined into a safety rate. Dropdowns use styled listboxes with pointer/touch selection, arrow keys, Home/End, Enter, Escape, Tab and first-letter navigation. The assistant launcher stays fixed at the bottom right on every page; API documentation is not linked in the product UI.

Automatic starting-scenario matching compares input conditions only, using per-fuel feature ranges to normalize differences. It never selects for an outcome or prediction score. Matching NASA evidence for the submitted inputs is retrieved by the backend after the user requests results.

The Material Advisor uses the original fixed closeness-weighted evidence order. No ranking selector is shown. The explanation above results describes how test count and matching conditions determine order, and each card explains its rank. Flame outcomes remain prominent but do not drive the ranking.
