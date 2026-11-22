import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import Field, { ErrorNote, PrimaryButton } from "../components/Field";
import { useAuth } from "../context/AuthContext";

export default function Register() {
  const { student, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (student) return <Navigate to="/dashboard" replace />;

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (form.password.length < 8) return setError("Use a password with at least 8 characters.");
    setBusy(true);
    try {
      await register(form.name, form.email, form.password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Free for students. Takes under a minute."
      footer={<>Already have an account? <Link to="/login" className="font-semibold text-ink underline">Log in</Link></>}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <ErrorNote>{error}</ErrorNote>
        <Field label="Full name" required maxLength={100} autoComplete="name"
          value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Field label="Email" type="email" required autoComplete="email" placeholder="you@college.edu"
          value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Field label="Password" type="password" required autoComplete="new-password" placeholder="At least 8 characters"
          value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <PrimaryButton busy={busy}>{busy ? "Creating account…" : "Create account"}</PrimaryButton>
      </form>
    </AuthLayout>
  );
}
