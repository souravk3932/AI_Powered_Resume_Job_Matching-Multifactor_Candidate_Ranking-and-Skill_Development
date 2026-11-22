const jwt = require("jsonwebtoken");

// Guard for protected routes. The browser sends: Authorization: Bearer <token>
// If the token is valid, we store the student's id in req.studentId.
// Every later query uses this id, so a student can only touch their own data.
function requireAuth(req, res, next) {
  const header = req.headers.authorization || "";
  const [scheme, token] = header.split(" ");

  if (scheme !== "Bearer" || !token) {
    return res.status(401).json({ error: "Login required" });
  }
  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET);
    req.studentId = payload.sub;
    next();
  } catch {
    return res.status(401).json({ error: "Invalid or expired token" });
  }
}

module.exports = requireAuth;
