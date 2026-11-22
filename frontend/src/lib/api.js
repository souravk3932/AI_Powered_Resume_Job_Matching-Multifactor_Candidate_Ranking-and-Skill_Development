// One helper for all backend calls. It adds the login token automatically.
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

export function getToken() {
  return localStorage.getItem("token");
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_URL}/api${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Cannot reach the server. Is the backend running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // No JSON error body usually means an old/wrong server answered (e.g. 404 page)
    const fallback = `Server replied ${res.status} without details. Restart the backend and try again.`;
    const err = new Error(data.error || fallback);
    err.status = res.status;
    throw err;
  }
  return data;
}
