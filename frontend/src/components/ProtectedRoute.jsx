import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

// Wrap a page with this: not logged in -> sent to the login page
export default function ProtectedRoute({ children }) {
  const { student, loading } = useAuth();
  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;
  return student ? children : <Navigate to="/login" replace />;
}
