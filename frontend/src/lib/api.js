// One helper for all backend calls. It adds the login token automatically.
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

export function getToken() {
  return localStorage.getItem("token");
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// body can be a plain object (sent as JSON) or FormData (used for file uploads)
export async function api(path, { method = "GET", body } = {}) {
  const headers = authHeaders();
  const isForm = body instanceof FormData;
  // For FormData the browser sets the Content-Type itself (it needs a special boundary)
  if (body && !isForm) headers["Content-Type"] = "application/json";

  let res;
  try {
    res = await fetch(`${API_URL}/api${path}`, {
      method,
      headers,
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
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

// Open a protected PDF in a new tab. A plain link can't send our login token,
// so we fetch the file with the token and show it from memory.
export async function openPdf(path) {
  const tab = window.open("", "_blank"); // open now so popup blockers allow it
  try {
    const res = await fetch(`${API_URL}/api${path}`, { headers: authHeaders() });
    if (!res.ok) throw new Error("Could not open the PDF");
    const url = URL.createObjectURL(await res.blob());
    tab.location.href = url;
  } catch (err) {
    tab?.close();
    throw err;
  }
}
