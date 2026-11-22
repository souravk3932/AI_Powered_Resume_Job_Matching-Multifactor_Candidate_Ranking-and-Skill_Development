const express = require("express");
const Student = require("../models/Student");
const requireAuth = require("../middleware/auth");

const router = express.Router();
router.use(requireAuth); // every route below needs a valid login

// Only these profile fields can be edited (nothing else is accepted)
const PROFILE_FIELDS = ["phone", "college", "degree", "graduationYear", "careerGoal", "about"];

// GET /api/profile  -> my own profile
router.get("/", async (req, res) => {
  const student = await Student.findById(req.studentId).select("name email profile createdAt");
  if (!student) return res.status(404).json({ error: "Student not found" });
  res.json({ student });
});

// PUT /api/profile  -> update my own name/profile
router.put("/", async (req, res) => {
  try {
    const update = {};
    if (req.body.name !== undefined) {
      const name = String(req.body.name).trim();
      if (!name || name.length > 100) return res.status(400).json({ error: "Invalid name" });
      update.name = name;
    }
    const incoming = req.body.profile || {};
    for (const field of PROFILE_FIELDS) {
      if (incoming[field] !== undefined) update[`profile.${field}`] = incoming[field];
    }

    const student = await Student.findByIdAndUpdate(
      req.studentId,
      { $set: update },
      { new: true, runValidators: true }
    ).select("name email profile");
    if (!student) return res.status(404).json({ error: "Student not found" });
    res.json({ student });
  } catch (err) {
    if (err.name === "ValidationError") return res.status(400).json({ error: err.message });
    console.error("profile error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

module.exports = router;
