// Load values from the .env file (like PORT) into process.env
require("dotenv").config();

const express = require("express");
const cors = require("cors");
const mongoose = require("mongoose");
const connectDB = require("./config/db");

connectDB();

const app = express();

app.use(cors());          // allow the React frontend to talk to this server
app.use(express.json());  // let the server read JSON sent by the frontend

app.use("/api/auth", require("./routes/auth"));
app.use("/api/profile", require("./routes/profile"));
app.use("/api/resumes", require("./routes/resumes"));
app.use("/api/jds", require("./routes/jds"));

// Health check: a simple "are you alive?" route
app.get("/api/health", (req, res) => {
  // readyState 1 means "connected" in mongoose
  const database = mongoose.connection.readyState === 1 ? "connected" : "not connected";
  res.json({ service: "backend", status: "ok", database, time: new Date().toISOString() });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Backend running on http://localhost:${PORT}`);
});
