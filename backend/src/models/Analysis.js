const mongoose = require("mongoose");

// One comparison of ONE resume version against ONE job description.
// Every run creates a NEW record and old ones are never changed, so the student can look back and
// see how results changed over time. Later phases add the factor scores to this same record.
const analysisSchema = new mongoose.Schema(
  {
    studentId: { type: mongoose.Schema.Types.ObjectId, ref: "Student", required: true, index: true },
    resumeId: { type: mongoose.Schema.Types.ObjectId, ref: "Resume", required: true },
    resumeVersionId: { type: mongoose.Schema.Types.ObjectId, ref: "ResumeVersion", required: true },
    versionNo: { type: Number, required: true },
    jdId: { type: mongoose.Schema.Types.ObjectId, ref: "JobDescription", required: true },

    // Names copied at the time of the run, so the history still reads well if something is renamed later
    resumeName: { type: String, default: "" },
    jobTitle: { type: String, default: "" },
    organization: { type: String, default: "" },

    // The skill match: every requirement with its status, method, evidence and reason
    skillMatch: { type: mongoose.Schema.Types.Mixed, select: false },
    summary: { type: mongoose.Schema.Types.Mixed, default: {} }, // counts of matched / partial / missing

    // EXACT copies of the two AI readings this analysis was built from. Re-scoring later uses these,
    // so it still works even if the student re-analyses the resume or job afterwards.
    resumeProfileSnapshot: { type: mongoose.Schema.Types.Mixed, select: false },
    jdProfileSnapshot: { type: mongoose.Schema.Types.Mixed, select: false },

    // Every scoring run is APPENDED here and never edited: { at, trigger, result }.
    // trigger: "initial" now; "role_change" when the student picks another role; Phase 11 adds "after_assessment".
    scoreSnapshots: { type: [mongoose.Schema.Types.Mixed], select: false, default: [] },
    // Short summary of the newest snapshot, for lists: { overall, lowerBound, coverage, roleProfile }
    latestScore: { type: mongoose.Schema.Types.Mixed, default: null },

    engineVersion: { type: String, default: "" },
    catalogVersion: { type: String, default: "" },
    embeddingModel: { type: String, default: "" },
    // Which AI readings of the two documents this analysis was built from (for reproducibility)
    inputs: { type: mongoose.Schema.Types.Mixed, default: {} },
    warnings: { type: [String], default: [] },
    status: { type: String, enum: ["done"], default: "done" },
  },
  { timestamps: true }
);

module.exports = mongoose.model("Analysis", analysisSchema);
