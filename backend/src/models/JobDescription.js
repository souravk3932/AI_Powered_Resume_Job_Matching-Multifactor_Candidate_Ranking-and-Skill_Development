const mongoose = require("mongoose");
const extractionSchema = require("./extractionSchema");
const profileSchema = require("./profileSchema");

// A job description (JD) saved by a student. It is never edited after saving
// (only the title/organization can change), because later analyses will point
// at this exact text. To change the text, save a new JD.
const jobDescriptionSchema = new mongoose.Schema(
  {
    studentId: { type: mongoose.Schema.Types.ObjectId, ref: "Student", required: true, index: true },
    title: { type: String, required: true, trim: true, maxlength: 150 },
    organization: { type: String, trim: true, maxlength: 150, default: "" }, // optional

    source: { type: String, enum: ["text", "pdf"], required: true },

    // The text the student pasted (empty for PDF JDs; their text is in extraction.text)
    text: { type: String, default: "", maxlength: 20000 },
    // What the text reader found (cleaned text + sections), filled right after saving
    extraction: { type: extractionSchema, default: () => ({}) },
    // What the AI understood: required skills, responsibilities... (claims + quotes, not verified facts)
    profile: { type: profileSchema, default: () => ({}) },

    // Only for source = "pdf"
    originalFileName: { type: String, maxlength: 200 },
    storedName: { type: String },
    fileSize: { type: Number },
    fileHash: { type: String },
  },
  { timestamps: true }
);

module.exports = mongoose.model("JobDescription", jobDescriptionSchema);
