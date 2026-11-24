const mongoose = require("mongoose");

// How we store "what the AI read from a resume" (skills, education, projects...).
// These are CLAIMS made by an AI, each with a quote and a status, never verified facts.
// The big `data` field is hidden from normal queries (select: false) so lists stay fast.
// Ask for it with .select("+profile.data").
const profileSchema = new mongoose.Schema(
  {
    status: { type: String, enum: ["not_started", "done", "failed"], default: "not_started" },
    data: { type: mongoose.Schema.Types.Mixed, select: false }, // { technical_skills: [...], education: [...], ... }
    counts: { type: mongoose.Schema.Types.Mixed, default: {} },     // how many items per category
    needsReview: { type: Number, default: 0 },                       // items whose quote was not found in the resume
    warnings: { type: [String], default: [] },
    redactions: { type: mongoose.Schema.Types.Mixed, default: {} }, // how many personal details were hidden before sending
    provider: { type: String, default: "" },
    model: { type: String, default: "" },
    promptVersion: { type: String, default: "" },
    analysedAt: { type: Date },
    error: { type: String, default: "" },
  },
  { _id: false }
);

module.exports = profileSchema;
