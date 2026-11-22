import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import Field, { ErrorNote, PrimaryButton } from "../components/Field";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { student, login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (student) return <Navigate to="/dashboard" replace />;

  async function handleSubmit(e) {
    e.preventDefault(); // stop the browser from reloading the page
    setError("");
    setBusy(true);
    try {
      await login(form.email, form.password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Log in to see your resumes and scores."
      footer={<>New here? <Link to="/register" className="font-semibold text-ink underline">Create an account</Link></>}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <ErrorNote>{error}</ErrorNote>
        <Field label="Email" type="email" required autoComplete="email" placeholder="you@college.edu"
          value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Field label="Password" type="password" required autoComplete="current-password"
          value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <PrimaryButton busy={busy}>{busy ? "Logging in…" : "Log in"}</PrimaryButton>
      </form>
    </AuthLayout>
  );
}
