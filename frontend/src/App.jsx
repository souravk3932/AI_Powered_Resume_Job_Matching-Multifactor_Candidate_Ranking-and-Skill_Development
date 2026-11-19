import { useEffect, useState } from "react";

// Address of our Node backend (later this will come from an env variable)
const BACKEND_URL = "http://localhost:5000";

export default function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  // Runs once when the page opens: ask the backend "are you alive?"
  useEffect(() => {
    fetch(`${BACKEND_URL}/api/health`)
      .then((res) => res.json())
      .then(setHealth)
      .catch(() => setError("Cannot reach backend. Is it running?"));
  }, []);

  return (
    <main className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
      <div className="bg-white rounded-xl shadow p-8 max-w-md w-full">
        <h1 className="text-xl font-bold text-slate-800">
          Resume–Job Compatibility System
        </h1>
        <p className="text-sm text-slate-500 mb-4">Phase 1 – service health</p>
        {error && <p className="text-red-600">{error}</p>}
        {health && (
          <ul className="text-slate-700">
            <li>Backend: <b>{health.status}</b></li>
            <li>Database: <b>{health.database}</b></li>
          </ul>
        )}
        {!health && !error && <p>Checking…</p>}
      </div>
    </main>
  );
}
