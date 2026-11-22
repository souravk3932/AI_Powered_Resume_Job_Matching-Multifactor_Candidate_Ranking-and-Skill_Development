const mongoose = require("mongoose");

// A Student record in the "students" collection.
// The profile fields are optional: students fill them in later.
const studentSchema = new mongoose.Schema(
  {
    name: { type: String, required: true, trim: true, maxlength: 100 },
    email: { type: String, required: true, unique: true, lowercase: true, trim: true },
    // We NEVER store the real password, only its hash
    passwordHash: { type: String, required: true, select: false },
    profile: {
      phone: { type: String, trim: true, maxlength: 20, default: "" },
      college: { type: String, trim: true, maxlength: 150, default: "" },
      degree: { type: String, trim: true, maxlength: 100, default: "" },
      graduationYear: { type: Number, min: 1990, max: 2100 },
      careerGoal: { type: String, trim: true, maxlength: 200, default: "" },
      about: { type: String, trim: true, maxlength: 1000, default: "" },
    },
  },
  { timestamps: true } // adds createdAt and updatedAt automatically
);

module.exports = mongoose.model("Student", studentSchema);
