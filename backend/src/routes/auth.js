const express = require("express");
const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");
const rateLimit = require("express-rate-limit");
const Student = require("../models/Student");

const router = express.Router();

// Max 20 register/login attempts per 15 minutes per IP (stops password guessing)
router.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 20, standardHeaders: true, legacyHeaders: false }));

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Make the "ID card" (JWT) for a student
function makeToken(studentId) {
  return jwt.sign({ sub: String(studentId) }, process.env.JWT_SECRET, {
    expiresIn: process.env.JWT_EXPIRES_IN || "7d",
  });
}

// POST /api/auth/register
router.post("/register", async (req, res) => {
  try {
    const name = String(req.body.name || "").trim();
    const email = String(req.body.email || "").trim().toLowerCase();
    const password = String(req.body.password || "");

    if (!name || name.length > 100) return res.status(400).json({ error: "Name is required (max 100 characters)" });
    if (!EMAIL_RE.test(email)) return res.status(400).json({ error: "Enter a valid email" });
    if (password.length < 8 || password.length > 72) {
      return res.status(400).json({ error: "Password must be 8 to 72 characters" });
    }

    if (await Student.exists({ email })) {
      return res.status(409).json({ error: "This email is already registered" });
    }

    const passwordHash = await bcrypt.hash(password, 10);
    const student = await Student.create({ name, email, passwordHash });
    res.status(201).json({ token: makeToken(student._id), student: { id: student._id, name, email } });
  } catch (err) {
    console.error("register error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

// POST /api/auth/login
router.post("/login", async (req, res) => {
  try {
    const email = String(req.body.email || "").trim().toLowerCase();
    const password = String(req.body.password || "");

    // passwordHash is hidden by default, so we ask for it explicitly here
    const student = await Student.findOne({ email }).select("+passwordHash");
    const ok = student && (await bcrypt.compare(password, student.passwordHash));

    // Same message for "no such email" and "wrong password" (don't leak which emails exist)
    if (!ok) return res.status(401).json({ error: "Wrong email or password" });

    res.json({ token: makeToken(student._id), student: { id: student._id, name: student.name, email: student.email } });
  } catch (err) {
    console.error("login error:", err.message);
    res.status(500).json({ error: "Something went wrong" });
  }
});

module.exports = router;
