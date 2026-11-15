// Thin client for the FastAPI backend (api/firesafe_api.py). Every call returns parsed JSON or throws an ApiError.
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
    res = await fetch(BASE + path, { ...options, headers: { "content-type": "application/json", ...(options.headers || {}) } });
  } catch {
    throw new ApiError(0, [{ field: null, message: "Can't reach the server. Is the backend running on port 8000?" }]);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const errors = body?.errors || (typeof detail === "string" ? [{ field: null, message: detail }]
      : Array.isArray(detail) ? detail.map((d) => ({ field: d.loc?.slice(1).join("."), message: d.msg })) : null);
    throw new ApiError(res.status, errors);
  }
  return body;
}

const get = (path, params) => request(path + (params ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)) : ""));
const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body) });

export const fs = {
  options: () => get("/api/fs/options"),
  advisor: (body) => post("/api/fs/advisor", body),
  explain: (result) => post("/api/fs/advisor/explain", { result }),
  predictSolid: (body) => post("/api/fs/predict/solid", body),
  predictFlex: (body) => post("/api/fs/predict/flex", body),
  catalog: () => get("/api/fs/catalog"),
  solids: () => get("/api/fs/solids"),
  flex: () => get("/api/fs/flex"),
  chat: (message, session_id, advisor_result) => post("/api/fs/chat", { message, session_id, advisor_result }),
  clearChat: (id) => request(`/api/fs/chat/${id}`, { method: "DELETE" }),
};
