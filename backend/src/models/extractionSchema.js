const mongoose = require("mongoose");

// How we store "what the text reader found". Shared by ResumeVersion and JobDescription.
// The big fields (text, sections) are hidden from normal queries (select: false),
// so lists stay fast. Ask for them explicitly with .select("+extraction.text +extraction.sections").

const sectionSchema = new mongoose.Schema(
  { name: String, heading: String, text: String },
  { _id: false }
);

const extractionSchema = new mongoose.Schema(
  {
    status: { type: String, enum: ["not_started", "done", "failed"], default: "not_started" },
    text: { type: String, select: false },          // cleaned full text
    sections: { type: [sectionSchema], select: false },
    sectionNames: { type: [String], default: [] },  // small list, always available
    expectedNotFound: { type: [String], default: [] },
    headingsRecognised: { type: Boolean, default: false },
    pageCount: { type: Number, default: 0 },
    pagesRead: { type: Number, default: 0 },
    charCount: { type: Number, default: 0 },
    warnings: { type: [String], default: [] },
    scannedSuspected: { type: Boolean, default: false },
    extractorVersion: { type: String, default: "" },
    extractedAt: { type: Date },
    error: { type: String, default: "" },
  },
  { _id: false }
);

module.exports = extractionSchema;
