const mongoose = require("mongoose");

// A job description (JD) saved by a student. It is never edited after saving
// (only the title/organization can change), because later analyses will point
// at this exact text. To change the text, save a new JD.
const jobDescriptionSchema = new mongoose.Schema(
  {
    studentId: { type: mongoose.Schema.Types.ObjectId, ref: "Student", required: true, index: true },
    title: { type: String, required: true, trim: true, maxlength: 150 },
    organization: { type: String, trim: true, maxlength: 150, default: "" }, // optional

    source: { type: String, enum: ["text", "pdf"], required: true },

    // Pasted JDs store their text now. PDF JDs get their text in Phase 5
    // (Python extraction), so for them this stays empty until then.
    text: { type: String, default: "", maxlength: 20000 },
    extractionStatus: { type: String, enum: ["not_needed", "pending"], required: true },

    // Only for source = "pdf"
    originalFileName: { type: String, maxlength: 200 },
    storedName: { type: String },
    fileSize: { type: Number },
    fileHash: { type: String },
  },
  { timestamps: true }
);

module.exports = mongoose.model("JobDescription", jobDescriptionSchema);
