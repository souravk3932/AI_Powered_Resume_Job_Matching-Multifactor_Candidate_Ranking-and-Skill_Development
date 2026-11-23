const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const multer = require("multer");

const MAX_PDF_BYTES = 5 * 1024 * 1024; // 5 MB
const UPLOAD_ROOT = path.join(__dirname, "..", "..", "uploads");
// "kind" is the sub-folder: "resumes" or "jds". Only these two are allowed.
const KINDS = ["resumes", "jds"];
function kindDir(kind) {
  if (!KINDS.includes(kind)) throw new Error("Unknown upload kind");
  return path.join(UPLOAD_ROOT, kind);
}

// Step 1: multer keeps the file in memory only (nothing touches the disk yet)
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_PDF_BYTES, files: 1 },
});

// Wrapper so multer errors (like "file too big") become clean JSON replies
function receivePdf(req, res, next) {
  upload.single("file")(req, res, (err) => {
    if (!err) return next();
    if (err.code === "LIMIT_FILE_SIZE") return res.status(413).json({ error: "PDF is too large (max 5 MB)" });
    return res.status(400).json({ error: "Upload failed. Send one file in the 'file' field." });
  });
}

// Step 2: check that it is REALLY a PDF (a real PDF starts with the bytes "%PDF-").
// We do not trust the file name or the type the browser claims.
function isRealPdf(buffer) {
  return buffer && buffer.length > 8 && buffer.subarray(0, 5).toString("latin1") === "%PDF-";
}

// Step 3: save to disk under a RANDOM name inside the student's own folder.
// The original file name is never used as a path (prevents path tricks).
function savePdf(studentId, buffer, kind = "resumes") {
  const dir = path.join(kindDir(kind), String(studentId));
  fs.mkdirSync(dir, { recursive: true });
  const storedName = `${crypto.randomBytes(16).toString("hex")}.pdf`;
  fs.writeFileSync(path.join(dir, storedName), buffer);
  const fileHash = crypto.createHash("sha256").update(buffer).digest("hex");
  return { storedName, fileHash };
}

function pdfPath(studentId, storedName, kind = "resumes") {
  return path.join(kindDir(kind), String(studentId), path.basename(storedName));
}

function deletePdf(studentId, storedName, kind = "resumes") {
  fs.rmSync(pdfPath(studentId, storedName, kind), { force: true });
}

module.exports = { receivePdf, isRealPdf, savePdf, pdfPath, deletePdf, MAX_PDF_BYTES };
