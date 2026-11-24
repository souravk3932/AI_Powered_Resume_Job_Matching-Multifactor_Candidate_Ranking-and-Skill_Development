const express = require("express");
const mongoose = require("mongoose");
const requireAuth = require("../middleware/auth");
const Resume = require("../models/Resume");
const ResumeVersion = require("../models/ResumeVersion");
const JobDescription = require("../models/JobDescription");
const Analysis = require("../models/Analysis");
const { matchSkills, AiServiceError } = require("../utils/aiClient");

const router = express.Router();
router.use(requireAuth); // every analysis route needs a login

const MAX_ANALYSES_PER_STUDENT = 200;
const validId = (id) => mongoose.Types.ObjectId.isValid(id);

// Short form for lists, full form (with every requirement) for one analysis
function analysisView(a, { full = false } = {}) {
  return {
    id: a._id,
    resumeId: a.resumeId,
    versionNo: a.versionNo,
    jdId: a.jdId,
    resumeName: a.resumeName,
    jobTitle: a.jobTitle,
    organization: a.organization,
    summary: a.summary,
    engineVersion: a.engineVersion,
    embeddingModel: a.embeddingModel,
    warnings: a.warnings,
    createdAt: a.createdAt,
    ...(full ? { skillMatch: a.skillMatch, inputs: a.inputs } : {}),
  };
}

// POST /api/analyses  { resumeId, jdId, versionNo? }  -> compare one resume version with one job description
router.post("/", async (req, res) => {
  try {
    const { resumeId, jdId } = req.body || {};
    if (!validId(resumeId) || !validId(jdId)) return res.status(400).json({ error: "Choose a resume and a job description" });

    // Ownership: both must belong to the logged-in student
    const resume = await Resume.findOne({ _id: resumeId, studentId: req.studentId });
    const jd = await JobDescription.findOne({ _id: jdId, studentId: req.studentId }).select("+profile.data");
    if (!resume) return res.status(404).json({ error: "Resume not found" });
    if (!jd) return res.status(404).json({ error: "Job description not found" });

    const asked = req.body.versionNo; // optional: defaults to the resume's newest version
    const versionNo = asked != null && Number.isInteger(Number(asked)) ? Number(asked) : resume.currentVersionNo;
    const version = await ResumeVersion.findOne({ resumeId: resume._id, studentId: req.studentId, versionNo }).select("+profile.data");
    if (!version) return res.status(404).json({ error: "Resume version not found" });

    // Both documents must have been understood by the AI first
    if (version.profile?.status !== "done") return res.status(400).json({ error: "Open Resumes and click “Analyse with AI” on this resume first." });
    if (jd.profile?.status !== "done") return res.status(400).json({ error: "Open Jobs and click “Analyse with AI” on this job description first." });

    if ((await Analysis.countDocuments({ studentId: req.studentId })) >= MAX_ANALYSES_PER_STUDENT) {
      return res.status(400).json({ error: `You can keep up to ${MAX_ANALYSES_PER_STUDENT} analyses.` });
    }

    let result;
    try {
      result = await matchSkills(version.profile.data, jd.profile.data);
    } catch (err) {
      if (err instanceof AiServiceError) {
        console.error("match failed:", err.detail || err.message);
        return res.status(502).json({ error: err.userMessage });
      }
      throw err;
    }

    const analysis = await Analysis.create({
      studentId: req.studentId,
      resumeId: resume._id,
      resumeVersionId: version._id,
      versionNo,
      jdId: jd._id,
      resumeName: resume.name,
      jobTitle: jd.title,
      organization: jd.organization,
      skillMatch: result,
      summary: result.summary,
      engineVersion: result.engine_version,
      catalogVersion: result.catalog_version,
      embeddingModel: result.embedding_model || "",
      warnings: result.warnings,
      inputs: {
        resumeProfile: { promptVersion: version.profile.promptVersion, model: version.profile.model, analysedAt: version.profile.analysedAt },
        jdProfile: { promptVersion: jd.profile.promptVersion, model: jd.profile.model, analysedAt: jd.profile.analysedAt },
      },
    });
    res.status(201).json({ analysis: analysisView(analysis, { full: true }) });
  } catch (err) {
    console.error("create analysis error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

// GET /api/analyses -> my past analyses, newest first (short form)
router.get("/", async (req, res) => {
  const list = await Analysis.find({ studentId: req.studentId }).sort({ createdAt: -1 }).limit(100);
  res.json({ analyses: list.map((a) => analysisView(a)) });
});

// GET /api/analyses/:id -> one analysis with every requirement, evidence and reason
router.get("/:id", async (req, res) => {
  if (!validId(req.params.id)) return res.status(404).json({ error: "Analysis not found" });
  const a = await Analysis.findOne({ _id: req.params.id, studentId: req.studentId }).select("+skillMatch");
  if (!a) return res.status(404).json({ error: "Analysis not found" });
  res.json({ analysis: analysisView(a, { full: true }) });
});

module.exports = router;
