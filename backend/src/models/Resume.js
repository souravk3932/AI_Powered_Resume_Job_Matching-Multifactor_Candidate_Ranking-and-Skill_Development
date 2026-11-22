const mongoose = require("mongoose");

// A "Resume" is the folder-like container, e.g. "Full Stack Resume".
// The actual PDF files live in ResumeVersion (one per upload).
const resumeSchema = new mongoose.Schema(
  {
    studentId: { type: mongoose.Schema.Types.ObjectId, ref: "Student", required: true, index: true },
    name: { type: String, required: true, trim: true, maxlength: 100 },
    targetRole: { type: String, trim: true, maxlength: 100, default: "" }, // e.g. "Data Analyst"
    currentVersionNo: { type: Number, default: 1 },
  },
  { timestamps: true }
);

module.exports = mongoose.model("Resume", resumeSchema);
