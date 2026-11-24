// Asks the AI service to understand a resume's text (skills, education, projects...) and stores the result.
// Requires the text to have been read already (services/extraction.js).

const { extractProfile, AiServiceError } = require("../utils/aiClient");

// Groq allows only a few thousand tokens per minute, so we send ONE request at a time.
// Each call waits for the previous one to finish (a tiny queue).
let queue = Promise.resolve();
function runOneAtATime(task) {
  const result = queue.then(task, task);
  queue = result.catch(() => {}); // keep the queue alive even if this task fails
  return result;
}

function toStored(r) {
  return {
    status: "done",
    data: r.profile,
    counts: r.counts,
    needsReview: r.needs_review,
    warnings: r.warnings,
    redactions: r.redactions,
    provider: r.provider,
    model: r.model,
    promptVersion: r.prompt_version,
    analysedAt: new Date(),
    error: "",
  };
}

function toFailed(err) {
  const known = err instanceof AiServiceError;
  console.error("profile extraction failed:", known ? err.detail || err.message : err.message);
  return {
    status: "failed",
    counts: {},
    warnings: [],
    redactions: {},
    analysedAt: new Date(),
    error: known ? err.userMessage : "Something went wrong while analysing this resume.",
  };
}

// `doc` (a resume version or a job description) must be loaded with "+extraction.text".
// kind is "resume" or "jd". Never throws: a failure is saved so the student can retry.
async function analyzeDocument(doc, kind) {
  const text = doc.extraction?.text;
  if (doc.extraction?.status !== "done" || !text) {
    const what = kind === "jd" ? "job description" : "resume";
    doc.profile = toFailed(new AiServiceError(`Read the ${what} text first, then analyse it.`, "no text"));
  } else {
    try {
      doc.profile = toStored(await runOneAtATime(() => extractProfile(text, kind)));
    } catch (err) {
      doc.profile = toFailed(err);
    }
  }
  await doc.save();
  return doc;
}

const analyzeResumeVersion = (version) => analyzeDocument(version, "resume");
const analyzeJd = (jd) => analyzeDocument(jd, "jd");

// Small summary for lists (no big data)
function profileSummary(p) {
  const x = p || {};
  return {
    status: x.status || "not_started",
    counts: x.counts || {},
    needsReview: x.needsReview || 0,
    warnings: x.warnings || [],
    redactions: x.redactions || {},
    provider: x.provider || "",
    model: x.model || "",
    promptVersion: x.promptVersion || "",
    analysedAt: x.analysedAt || null,
    error: x.error || "",
  };
}

// Full view: includes the claims themselves
function profileDetail(p) {
  return { ...profileSummary(p), data: p?.data || {} };
}

module.exports = { analyzeResumeVersion, analyzeJd, profileSummary, profileDetail };
