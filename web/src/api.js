// Thin client for the FastAPI backend. Every call returns parsed JSON or throws
// an ApiError whose `errors` is [{field, message}] (the backend's error shape).
const BASE = import.meta.env.VITE_API_URL || "";

export class ApiError extends Error {
  constructor(status, errors) {
    super(errors?.map((e) => e.message).join("; ") || `Request failed (${status})`);
    this.status = status;
    this.errors = errors || [];
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      ...options,
      headers: { "content-type": "application/json", ...(options.headers || {}) },
    });
  } catch {
    throw new ApiError(0, [{ field: null, message: "Can't reach the API. Is the backend running on port 8000?" }]);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.errors);
  return body;
}

const get = (path, params) => {
  const q = params
    ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)).toString()
    : "";
  return request(path + q);
};
const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => get("/api/health"),
  options: () => get("/api/options"),
  investigations: (params) => get("/api/investigations", params),
  investigation: (id) => get(`/api/investigations/${encodeURIComponent(id)}`),
  experiments: (params) => get("/api/experiments", params),
  experiment: (id) => get(`/api/experiments/${id}`),
  compare: (a, b) => post("/api/compare", { experiment_a: a, experiment_b: b }),
  search: (q, params) => get("/api/search", { q, ...params }),
  coverage: (dataset) => get("/api/coverage", { dataset }),
  advisor: (body) => post("/api/advisor", body),
  similarSolid: (body) => post("/api/similar/solid", body),
  predictExtinction: (body) => post("/api/predict/extinction", body),
  predictionControls: (body) => post("/api/predict/controls", body),
  predictBurnTime: (body) => post("/api/predict/burn-time", body),
  whatIf: (body) => post("/api/what-if", body),
  model: () => get("/api/model"),
  chat: (messages, context) => post("/api/chat", { messages, context }),
};
