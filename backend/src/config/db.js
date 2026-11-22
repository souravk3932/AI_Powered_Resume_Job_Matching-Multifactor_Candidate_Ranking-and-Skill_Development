const dns = require("node:dns");
const mongoose = require("mongoose");

// Some Windows/router DNS setups refuse the SRV lookup Atlas needs
// (error: querySrv ECONNREFUSED). Use public DNS for Node only.
dns.setServers(["8.8.8.8", "1.1.1.1"]);

// Connect to MongoDB using the address stored in .env (never hard-code it!)
async function connectDB() {
  const uri = process.env.MONGODB_URI;
  if (!uri) {
    console.warn("MONGODB_URI is empty in .env - database not connected.");
    return;
  }
  try {
    await mongoose.connect(uri);
    console.log("MongoDB connected");
  } catch (err) {
    console.error("MongoDB connection failed:", err.message);
  }
}

module.exports = connectDB;
