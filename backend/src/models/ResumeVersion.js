const mongoose = require("mongoose");
const extractionSchema = require("./extractionSchema");

// One uploaded PDF. Versions are never edited: a new upload = a new version.
// Later phases (extraction, analysis) will point at a specific version.
const resumeVersionSchema = new mongoose.Schema(
  {
    resumeId: { type: mongoose.Schema.Types.ObjectId, ref: "Resume", required: true, index: true },
    studentId: { type: mongoose.Schema.Types.ObjectId, ref: "Student", required: true, index: true },
    versionNo: { type: Number, required: true },
    originalFileName: { type: String, maxlength: 200 }, // shown to the student only
    storedName: { type: String, required: true },       // random name on disk
    fileSize: { type: Number, required: true },
    fileHash: { type: String, required: true },         // SHA-256, detects identical files
    uploadedAt: { type: Date, default: Date.now },
    // What the text reader found in this PDF (filled right after upload)
    extraction: { type: extractionSchema, default: () => ({}) },
  },
  { timestamps: false }
);

// A resume can't have two versions with the same number
resumeVersionSchema.index({ resumeId: 1, versionNo: 1 }, { unique: true });

module.exports = mongoose.model("ResumeVersion", resumeVersionSchema);
