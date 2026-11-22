import { useCallback, useEffect, useState } from "react";
import AppHeader from "../components/AppHeader";
import Field, { ErrorNote } from "../components/Field";
import ResumeCard from "../components/ResumeCard";
import { api } from "../lib/api";

const MAX_BYTES = 5 * 1024 * 1024;

export default function Resumes() {
  const [resumes, setResumes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState({ name: "", targetRole: "", file: null });
  const [formError, setFormError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [fileKey, setFileKey] = useState(0); // changing this clears the file input

  const load = useCallback(async () => {
    try {
      const data = await api("/resumes");
      setResumes(data.resumes);
      setLoadError("");
    } catch (err) {
      setLoadError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function chooseFile(e) {
    const file = e.target.files[0] || null;
    setFormError("");
    if (file && file.size > MAX_BYTES) {
      setFormError("That PDF is larger than 5 MB.");
      setForm({ ...form, file: null });
      return;
    }
    // Pre-fill the name from the file name if the student hasn't typed one
    const guess = file ? file.name.replace(/\.pdf$/i, "") : "";
    setForm({ ...form, file, name: form.name || guess });
  }

  async function handleUpload(e) {
    e.preventDefault();
    setFormError("");
    if (!form.file) return setFormError("Choose a PDF file first.");
    setUploading(true);
    try {
      const body = new FormData();
      body.append("name", form.name);
      body.append("targetRole", form.targetRole);
      body.append("file", form.file);
      await api("/resumes", { method: "POST", body });
      setForm({ name: "", targetRole: "", file: null });
      setFileKey((k) => k + 1);
      await load();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="min-h-screen">
      <AppHeader />
      <main className="mx-auto max-w-5xl px-6 py-10">
        <h1 className="font-display text-3xl font-bold sm:text-4xl">Your resumes</h1>
        <p className="mt-1 max-w-xl text-slate">
          Keep one resume per role. Uploading a new version never replaces the old one, so earlier results stay valid.
        </p>

        <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_1.4fr]">
          <form onSubmit={handleUpload} className="h-fit space-y-4 rounded-2xl border border-line bg-white p-6">
            <h2 className="font-display text-xl font-bold">Add a resume</h2>
            <ErrorNote>{formError}</ErrorNote>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">PDF file (up to 5 MB)</span>
              <input key={fileKey} type="file" accept="application/pdf" onChange={chooseFile}
                className="w-full rounded-lg border border-dashed border-slate/40 bg-paper p-3 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-ink file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-white" />
            </label>
            <Field label="Resume name" required maxLength={100} placeholder="Full Stack Resume"
              value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Field label="Target role (optional)" maxLength={100} placeholder="Full Stack Developer"
              value={form.targetRole} onChange={(e) => setForm({ ...form, targetRole: e.target.value })} />
            <button disabled={uploading} className="w-full rounded-lg bg-ink px-4 py-3 font-semibold text-white hover:bg-ink-soft disabled:opacity-60">
              {uploading ? "Uploading…" : "Upload resume"}
            </button>
          </form>

          <section>
            <ErrorNote>{loadError}</ErrorNote>
            {loading && <p className="text-slate">Loading your resumes…</p>}
            {!loading && !loadError && resumes.length === 0 && (
              <div className="rounded-2xl border border-dashed border-slate/30 p-8">
                <p className="font-display text-lg font-bold">No resumes yet</p>
                <p className="mt-1 text-slate">Upload your first PDF on the left to get started.</p>
              </div>
            )}
            <ul className="space-y-4">
              {resumes.map((r) => <ResumeCard key={r.id} resume={r} onChanged={load} />)}
            </ul>
          </section>
        </div>
      </main>
    </div>
  );
}
