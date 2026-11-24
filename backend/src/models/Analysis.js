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
