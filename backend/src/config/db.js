const mongoose = require("mongoose");

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
