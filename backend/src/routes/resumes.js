const express = require("express");
const fs = require("fs");
const mongoose = require("mongoose");
const requireAuth = require("../middleware/auth");
const Resume = require("../models/Resume");
const ResumeVersion = require("../models/ResumeVersion");
const { receivePdf, isRealPdf, savePdf, pdfPath, deletePdf } = require("../utils/pdfUpload");

const router = express.Router();
router.use(requireAuth); // every resume route needs a login

const MAX_RESUMES_PER_STUDENT = 20;

// Reject ids that are not valid MongoDB ids before touching the database
function validId(id) {
  return mongoose.Types.ObjectId.isValid(id);
}

// Find a resume ONLY if it belongs to the logged-in student (ownership check)
function findOwnResume(req) {
  if (!validId(req.params.id)) return null;
  return Resume.findOne({ _id: req.params.id, studentId: req.studentId });
}

// Store the uploaded PDF and its version record. Returns the new version.
async function addVersion(req, resume, versionNo) {
  const { storedName, fileHash } = savePdf(req.studentId, req.file.buffer);
  try {
    return await ResumeVersion.create({
      resumeId: resume._id,
      studentId: req.studentId,
      versionNo,
      originalFileName: String(req.file.originalname || "resume.pdf").slice(0, 200),
      storedName,
      fileSize: req.file.size,
      fileHash,
    });
  } catch (err) {
    deletePdf(req.studentId, storedName); // don't leave an orphan file
    throw err;
  }
}

// Shape sent to the browser (never includes the stored file path)
function versionView(v) {
  return { versionNo: v.versionNo, originalFileName: v.originalFileName, fileSize: v.fileSize, uploadedAt: v.uploadedAt };
}

function resumeView(r, version) {
  return {
    id: r._id,
    name: r.name,
    targetRole: r.targetRole,
    currentVersionNo: r.currentVersionNo,
    createdAt: r.createdAt,
    currentVersion: version ? versionView(version) : null,
  };
}

// POST /api/resumes  (form-data: name, targetRole, file) -> new resume, version 1
router.post("/", receivePdf, async (req, res) => {
  try {
    const name = String(req.body.name || "").trim();
    const targetRole = String(req.body.targetRole || "").trim();
    if (!name || name.length > 100) return res.status(400).json({ error: "Give the resume a name (max 100 characters)" });
    if (targetRole.length > 100) return res.status(400).json({ error: "Target role is too long (max 100 characters)" });
    if (!req.file) return res.status(400).json({ error: "Attach a PDF file" });
    if (!isRealPdf(req.file.buffer)) return res.status(400).json({ error: "Only real PDF files are allowed" });

    if ((await Resume.countDocuments({ studentId: req.studentId })) >= MAX_RESUMES_PER_STUDENT) {
      return res.status(400).json({ error: `You can keep up to ${MAX_RESUMES_PER_STUDENT} resumes. Delete one first.` });
    }

    const resume = await Resume.create({ studentId: req.studentId, name, targetRole, currentVersionNo: 1 });
    try {
      const version = await addVersion(req, resume, 1);
      res.status(201).json({ resume: resumeView(resume, version) });
    } catch (err) {
      await Resume.deleteOne({ _id: resume._id }); // roll back
      throw err;
    }
  } catch (err) {
    console.error("create resume error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

// GET /api/resumes -> all my resumes with their latest version
router.get("/", async (req, res) => {
  const resumes = await Resume.find({ studentId: req.studentId }).sort({ updatedAt: -1 });
  const versions = await ResumeVersion.find({
    studentId: req.studentId,
    resumeId: { $in: resumes.map((r) => r._id) },
  });
  const key = (resumeId, no) => `${resumeId}:${no}`;
  const byKey = new Map(versions.map((v) => [key(v.resumeId, v.versionNo), v]));
  res.json({ resumes: resumes.map((r) => resumeView(r, byKey.get(key(r._id, r.currentVersionNo)))) });
});

// GET /api/resumes/:id -> one resume with ALL its versions
router.get("/:id", async (req, res) => {
  const resume = await findOwnResume(req);
  if (!resume) return res.status(404).json({ error: "Resume not found" });
  const versions = await ResumeVersion.find({ resumeId: resume._id, studentId: req.studentId }).sort({ versionNo: -1 });
  res.json({ resume: resumeView(resume, versions[0]), versions: versions.map(versionView) });
});

// POST /api/resumes/:id/versions  (form-data: file) -> adds a NEW version, old ones stay
router.post("/:id/versions", receivePdf, async (req, res) => {
  try {
    const resume = await findOwnResume(req);
    if (!resume) return res.status(404).json({ error: "Resume not found" });
    if (!req.file) return res.status(400).json({ error: "Attach a PDF file" });
    if (!isRealPdf(req.file.buffer)) return res.status(400).json({ error: "Only real PDF files are allowed" });

    // $inc is atomic: two uploads at the same moment still get different numbers
    const bumped = await Resume.findOneAndUpdate(
      { _id: resume._id, studentId: req.studentId },
      { $inc: { currentVersionNo: 1 } },
      { new: true }
    );
    const version = await addVersion(req, bumped, bumped.currentVersionNo);
    res.status(201).json({ resume: resumeView(bumped, version) });
  } catch (err) {
    console.error("add version error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

// GET /api/resumes/:id/versions/:versionNo/file -> download one of MY PDFs
router.get("/:id/versions/:versionNo/file", async (req, res) => {
  const resume = await findOwnResume(req);
  const versionNo = Number(req.params.versionNo);
  if (!resume || !Number.isInteger(versionNo)) return res.status(404).json({ error: "File not found" });
  const version = await ResumeVersion.findOne({ resumeId: resume._id, studentId: req.studentId, versionNo });
  if (!version) return res.status(404).json({ error: "File not found" });

  const file = pdfPath(req.studentId, version.storedName);
  if (!fs.existsSync(file)) return res.status(404).json({ error: "File is missing on the server" });
  res.setHeader("Content-Type", "application/pdf");
  res.setHeader("Content-Disposition", 'inline; filename="resume.pdf"');
  fs.createReadStream(file).pipe(res);
});

// PATCH /api/resumes/:id -> rename / change target role
router.patch("/:id", async (req, res) => {
  try {
    const resume = await findOwnResume(req);
    if (!resume) return res.status(404).json({ error: "Resume not found" });
    if (req.body.name !== undefined) {
      const name = String(req.body.name).trim();
      if (!name || name.length > 100) return res.status(400).json({ error: "Invalid name" });
      resume.name = name;
    }
    if (req.body.targetRole !== undefined) {
      const role = String(req.body.targetRole).trim();
      if (role.length > 100) return res.status(400).json({ error: "Target role is too long" });
      resume.targetRole = role;
    }
    await resume.save();
    const version = await ResumeVersion.findOne({ resumeId: resume._id, versionNo: resume.currentVersionNo });
    res.json({ resume: resumeView(resume, version) });
  } catch (err) {
    console.error("rename resume error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

// DELETE /api/resumes/:id?confirm=true -> delete the resume and ALL its versions/files
// Destructive, so it refuses unless the caller explicitly confirms.
router.delete("/:id", async (req, res) => {
  try {
    if (req.query.confirm !== "true") {
      return res.status(400).json({ error: "Deleting is permanent. Send confirm=true to continue." });
    }
    const resume = await findOwnResume(req);
    if (!resume) return res.status(404).json({ error: "Resume not found" });

    const versions = await ResumeVersion.find({ resumeId: resume._id, studentId: req.studentId });
    versions.forEach((v) => deletePdf(req.studentId, v.storedName));
    await ResumeVersion.deleteMany({ resumeId: resume._id, studentId: req.studentId });
    await Resume.deleteOne({ _id: resume._id, studentId: req.studentId });
    res.json({ deleted: true });
  } catch (err) {
    console.error("delete resume error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

module.exports = router;
