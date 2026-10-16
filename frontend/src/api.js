// All requests include credentials so the httpOnly session cookie set by
// the backend is sent automatically. VITE_API_BASE_URL must point at the
// deployed (or local) backend origin.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8787";

class ApiError extends Error {
  constructor(status, body) {
    super(typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body));
    this.status = status;
    this.body = body;
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  let body = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    throw new ApiError(res.status, body);
  }
  return body;
}

export const api = {
  login: (email, password) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request("/api/auth/me"),
  listVehicles: () => request("/api/vehicles"),
  getVehicle: (id) => request(`/api/vehicles/${id}`),
  updateVehicle: (id, data) =>
    request(`/api/vehicles/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  health: () => request("/api/health"),
};

export { ApiError };
