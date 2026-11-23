// Runs text extraction for a resume version or a job description and stores the result.
// Routes call these functions; these functions call the AI service (utils/aiClient).

const fs = require("fs");
const { pdfPath } = require("../utils/pdfUpload");
const { extractPdf, analyzeText, AiServiceError } = require("../utils/aiClient");

// Turn the AI service reply into the shape we store in MongoDB
function toStored(result) {
  return {
    status: "done",
    text: result.text,
    sections: result.sections,
    sectionNames: result.sections.map((s) => s.name),
    expectedNotFound: result.expected_not_found,
    headingsRecognised: result.headings_recognised,
    pageCount: result.page_count,
    pagesRead: result.pages_read,
    charCount: result.char_count,
    warnings: result.warnings,
    scannedSuspected: result.scanned_suspected,
    extractorVersion: result.extractor_version,
    extractedAt: new Date(),
    error: "",
  };
}

function toFailed(err) {
  const known = err instanceof AiServiceError;
  console.error("extraction failed:", known ? err.detail || err.message : err.message);
  return {
    status: "failed",
    error: known ? err.userMessage : "Something went wrong while reading this file.",
    sectionNames: [],
    expectedNotFound: [],
    warnings: [],
    extractedAt: new Date(),
  };
}

// Never throws: a failure is saved on the document so the student can see it and retry.
async function extractResumeVersion(version) {
  try {
    const buffer = fs.readFileSync(pdfPath(version.studentId, version.storedName, "resumes"));
    version.extraction = toStored(await extractPdf(buffer, "resume"));
  } catch (err) {
    version.extraction = toFailed(err);
  }
  await version.save();
  return version;
}

async function extractJd(jd) {
  try {
    if (jd.source === "pdf") {
      const buffer = fs.readFileSync(pdfPath(jd.studentId, jd.storedName, "jds"));
      jd.extraction = toStored(await extractPdf(buffer, "jd"));
    } else {
      jd.extraction = toStored(await analyzeText(jd.text, "jd"));
    }
  } catch (err) {
    jd.extraction = toFailed(err);
  }
  await jd.save();
  return jd;
}

// Small summary: safe to send in lists (no big text)
function extractionSummary(ex) {
  const e = ex || {};
  return {
    status: e.status || "not_started",
    sectionNames: e.sectionNames || [],
    expectedNotFound: e.expectedNotFound || [],
    pageCount: e.pageCount || 0,
    pagesRead: e.pagesRead || 0,
    charCount: e.charCount || 0,
    warnings: e.warnings || [],
    scannedSuspected: !!e.scannedSuspected,
    error: e.error || "",
    extractedAt: e.extractedAt || null,
  };
}

// Full view: includes the cleaned text and the sections (only when asked for)
function extractionDetail(ex) {
  return {
    ...extractionSummary(ex),
    text: ex?.text || "",
    sections: (ex?.sections || []).map((s) => ({ name: s.name, heading: s.heading, text: s.text })),
  };
}

module.exports = { extractResumeVersion, extractJd, extractionSummary, extractionDetail };
