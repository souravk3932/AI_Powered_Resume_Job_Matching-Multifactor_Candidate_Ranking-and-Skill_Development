const express = require("express");
const fs = require("fs");
const mongoose = require("mongoose");
const requireAuth = require("../middleware/auth");
const JobDescription = require("../models/JobDescription");
const { receivePdf, isRealPdf, savePdf, pdfPath, deletePdf } = require("../utils/pdfUpload");
const { extractJd, extractionSummary, extractionDetail } = require("../services/extraction");
const { analyzeJd, profileSummary, profileDetail } = require("../services/profile");

const router = express.Router();
router.use(requireAuth); // every JD route needs a login

const KIND = "jds"; // upload sub-folder
const MAX_JDS_PER_STUDENT = 50;
const MIN_TEXT = 50;
const MAX_TEXT = 20000;

// Find a JD ONLY if it belongs to the logged-in student (ownership check)
function findOwnJd(req) {
  if (!mongoose.Types.ObjectId.isValid(req.params.id)) return null;
  return JobDescription.findOne({ _id: req.params.id, studentId: req.studentId });
}

// Make pasted text consistent: any line-ending style, no hidden control characters
function cleanText(raw) {
  return String(raw || "")
    .replace(/\r\n?/g, "\n")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "")
    .trim();
}

// List view: short preview only. Detail view: full text.
function jdView(jd, { full = false } = {}) {
  return {
    id: jd._id,
    title: jd.title,
    organization: jd.organization,
    source: jd.source,
    extraction: extractionSummary(jd.extraction),
    profile: profileSummary(jd.profile),
    originalFileName: jd.originalFileName,
    fileSize: jd.fileSize,
    createdAt: jd.createdAt,
    ...(full ? { text: jd.text } : { preview: jd.text.slice(0, 200) }),
  };
}

// POST /api/jds   (form-data or JSON: title, organization?, and EITHER text OR a PDF in "file")
router.post("/", receivePdf, async (req, res) => {
  let saved = null;
  try {
    const body = req.body || {}; // Express 5 leaves body undefined when nothing was sent
    const title = String(body.title || "").trim();
    const organization = String(body.organization || "").trim();
    const text = cleanText(body.text);

    if (!title || title.length > 150) return res.status(400).json({ error: "Enter a job title (max 150 characters)" });
    if (organization.length > 150) return res.status(400).json({ error: "Organization name is too long (max 150 characters)" });

    const hasFile = !!req.file;
    if (hasFile && text) return res.status(400).json({ error: "Send either pasted text or a PDF, not both" });
    if (!hasFile && !text) return res.status(400).json({ error: "Paste the job description or attach a PDF" });

    if ((await JobDescription.countDocuments({ studentId: req.studentId })) >= MAX_JDS_PER_STUDENT) {
      return res.status(400).json({ error: `You can keep up to ${MAX_JDS_PER_STUDENT} job descriptions. Delete one first.` });
    }

    const doc = { studentId: req.studentId, title, organization };

    if (hasFile) {
      if (!isRealPdf(req.file.buffer)) return res.status(400).json({ error: "Only real PDF files are allowed" });
      saved = savePdf(req.studentId, req.file.buffer, KIND);
      Object.assign(doc, {
        source: "pdf",
        originalFileName: String(req.file.originalname || "job.pdf").slice(0, 200),
        storedName: saved.storedName,
        fileSize: req.file.size,
        fileHash: saved.fileHash,
      });
    } else {
      if (text.length < MIN_TEXT) return res.status(400).json({ error: `The job description is too short (at least ${MIN_TEXT} characters)` });
      if (text.length > MAX_TEXT) return res.status(400).json({ error: `The job description is too long (max ${MAX_TEXT} characters)` });
      Object.assign(doc, { source: "text", text });
    }

    const jd = await JobDescription.create(doc);
    await extractJd(jd); // read text and find sections now; never throws (a failure is saved on the JD)
    res.status(201).json({ jd: jdView(jd, { full: true }) });
  } catch (err) {
    if (saved) deletePdf(req.studentId, saved.storedName, KIND); // don't leave an orphan file
    console.error("create jd error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

// GET /api/jds -> all my JDs (newest first)
router.get("/", async (req, res) => {
  const jds = await JobDescription.find({ studentId: req.studentId }).sort({ createdAt: -1 });
  res.json({ jds: jds.map((j) => jdView(j)) });
});

// GET /api/jds/:id -> one JD with its full text
router.get("/:id", async (req, res) => {
  const jd = await findOwnJd(req);
  if (!jd) return res.status(404).json({ error: "Job description not found" });
  res.json({ jd: jdView(jd, { full: true }) });
});

// GET /api/jds/:id/file -> view the PDF of one of MY PDF-based JDs
router.get("/:id/file", async (req, res) => {
  const jd = await findOwnJd(req);
  if (!jd || jd.source !== "pdf") return res.status(404).json({ error: "File not found" });
  const file = pdfPath(req.studentId, jd.storedName, KIND);
  if (!fs.existsSync(file)) return res.status(404).json({ error: "File is missing on the server" });
  res.setHeader("Content-Type", "application/pdf");
  res.setHeader("Content-Disposition", 'inline; filename="job-description.pdf"');
  fs.createReadStream(file).pipe(res);
});

// GET /api/jds/:id/extraction -> the cleaned text and sections the reader found
router.get("/:id/extraction", async (req, res) => {
  if (!mongoose.Types.ObjectId.isValid(req.params.id)) return res.status(404).json({ error: "Job description not found" });
  const jd = await JobDescription.findOne({ _id: req.params.id, studentId: req.studentId })
    .select("+extraction.text +extraction.sections");
  if (!jd) return res.status(404).json({ error: "Job description not found" });
  res.json({ extraction: extractionDetail(jd.extraction) });
});

// POST /api/jds/:id/extract -> read the text again (for old JDs or after a failure)
router.post("/:id/extract", async (req, res) => {
  const jd = await findOwnJd(req);
  if (!jd) return res.status(404).json({ error: "Job description not found" });
  await extractJd(jd);
  res.json({ extraction: extractionSummary(jd.extraction) });
});

// GET /api/jds/:id/profile -> required skills, responsibilities... the AI found (with quotes and statuses)
router.get("/:id/profile", async (req, res) => {
  if (!mongoose.Types.ObjectId.isValid(req.params.id)) return res.status(404).json({ error: "Job description not found" });
  const jd = await JobDescription.findOne({ _id: req.params.id, studentId: req.studentId }).select("+profile.data");
  if (!jd) return res.status(404).json({ error: "Job description not found" });
  res.json({ profile: profileDetail(jd.profile) });
});

// POST /api/jds/:id/profile -> ask the AI to understand this job description (can be repeated)
router.post("/:id/profile", async (req, res) => {
  if (!mongoose.Types.ObjectId.isValid(req.params.id)) return res.status(404).json({ error: "Job description not found" });
  const jd = await JobDescription.findOne({ _id: req.params.id, studentId: req.studentId })
    .select("+extraction.text +profile.data");
  if (!jd) return res.status(404).json({ error: "Job description not found" });
  await analyzeJd(jd);
  res.json({ profile: profileSummary(jd.profile) });
});

// PATCH /api/jds/:id -> change title / organization only (the text never changes)
router.patch("/:id", async (req, res) => {
  try {
    const jd = await findOwnJd(req);
    if (!jd) return res.status(404).json({ error: "Job description not found" });
    if (req.body.title !== undefined) {
      const title = String(req.body.title).trim();
      if (!title || title.length > 150) return res.status(400).json({ error: "Invalid title" });
      jd.title = title;
    }
    if (req.body.organization !== undefined) {
      const org = String(req.body.organization).trim();
      if (org.length > 150) return res.status(400).json({ error: "Organization name is too long" });
      jd.organization = org;
    }
    await jd.save();
    res.json({ jd: jdView(jd) });
  } catch (err) {
    console.error("update jd error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

// DELETE /api/jds/:id?confirm=true -> permanent, so it needs explicit confirmation
router.delete("/:id", async (req, res) => {
  try {
    if (req.query.confirm !== "true") {
      return res.status(400).json({ error: "Deleting is permanent. Send confirm=true to continue." });
    }
    const jd = await findOwnJd(req);
    if (!jd) return res.status(404).json({ error: "Job description not found" });
    if (jd.source === "pdf") deletePdf(req.studentId, jd.storedName, KIND);
    await JobDescription.deleteOne({ _id: jd._id, studentId: req.studentId });
    res.json({ deleted: true });
  } catch (err) {
    console.error("delete jd error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

module.exports = router;
