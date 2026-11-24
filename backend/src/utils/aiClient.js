// The ONLY place where the Node backend talks to the Python AI service.
// Every call carries the secret X-Service-Key so the AI service knows it is us.

const TIMEOUT_MS = 30000;

// An error whose message is safe to show to the student
class AiServiceError extends Error {
  constructor(userMessage, detail) {
    super(userMessage);
    this.name = "AiServiceError";
    this.userMessage = userMessage;
    this.detail = detail; // technical detail, for the server log only
  }
}

async function call(path, init, timeoutMs = TIMEOUT_MS) {
  const base = process.env.AI_SERVICE_URL || "http://localhost:8000";
  let res;
  try {
    res = await fetch(`${base}${path}`, {
      ...init,
      headers: { ...(init.headers || {}), "X-Service-Key": process.env.AI_SERVICE_KEY || "" },
      signal: AbortSignal.timeout(timeoutMs), // never wait forever
    });
  } catch (err) {
    throw new AiServiceError(
      "The text reader is not reachable. Make sure the AI service is running, then try again.",
      err.message
    );
  }

  const body = await res.json().catch(() => ({}));
  if (res.ok) return body;

  if (res.status === 401) {
    throw new AiServiceError(
      "The AI service key is missing or does not match. Check AI_SERVICE_KEY in backend/.env and ai-service/.env.",
      `status ${res.status}`
    );
  }
  // 400/413/422/429/502/503 carry a readable message written by the AI service
  // (for example "password-protected", "too many requests", "GROQ_API_KEY is not set")
  const message = typeof body.detail === "string" ? body.detail : "The text reader could not process this file.";
  throw new AiServiceError(message, `status ${res.status}`);
}

// Send a PDF (as bytes). docType is "resume" or "jd".
function extractPdf(buffer, docType) {
  const form = new FormData(); // the browser-style form that carries a file
  form.append("doc_type", docType);
  form.append("file", new Blob([buffer], { type: "application/pdf" }), "document.pdf");
  return call("/internal/extract/document", { method: "POST", body: form });
}

// Send already-typed text (pasted job descriptions)
function analyzeText(text, docType) {
  return call("/internal/analyze/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, doc_type: docType }),
  });
}

// Resume text -> structured profile (skills, education...). The LLM can take a while, so allow 90 seconds.
function extractProfile(text) {
  return call(
    "/internal/extract/profile",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) },
    90000
  );
}

module.exports = { extractPdf, analyzeText, extractProfile, AiServiceError };
