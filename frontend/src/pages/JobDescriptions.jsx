import { useCallback, useEffect, useState } from "react";
import AppHeader from "../components/AppHeader";
import Field, { ErrorNote } from "../components/Field";
import JobCard from "../components/JobCard";
import { api } from "../lib/api";

const MAX_BYTES = 5 * 1024 * 1024;
const MIN_TEXT = 50;
const MAX_TEXT = 20000;
const EMPTY = { title: "", organization: "", text: "", file: null };

export default function JobDescriptions() {
  const [jds, setJds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [mode, setMode] = useState("text"); // "text" = paste, "pdf" = upload
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [fileKey, setFileKey] = useState(0); // changing this clears the file input

  const load = useCallback(async () => {
    try {
      setJds((await api("/jds")).jds);
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
    setForm({ ...form, file });
  }

  async function handleSave(e) {
    e.preventDefault();
    setFormError("");
    if (mode === "text" && form.text.trim().length < MIN_TEXT) {
      return setFormError(`Paste the full job description (at least ${MIN_TEXT} characters).`);
    }
    if (mode === "pdf" && !form.file) return setFormError("Choose a PDF file first.");

    setSaving(true);
    try {
      const body = new FormData();
      body.append("title", form.title);
      body.append("organization", form.organization);
      if (mode === "text") body.append("text", form.text);
      else body.append("file", form.file);
      await api("/jds", { method: "POST", body });
      setForm(EMPTY);
      setFileKey((k) => k + 1);
      await load();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const tab = (value, label) => (
    <button type="button" onClick={() => { setMode(value); setFormError(""); }}
      className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium ${mode === value ? "bg-white shadow-sm" : "text-slate"}`}>
      {label}
    </button>
  );

  return (
    <div className="min-h-screen">
      <AppHeader />
      <main className="mx-auto max-w-5xl px-6 py-10">
        <h1 className="font-display text-3xl font-bold sm:text-4xl">Job descriptions</h1>
        <p className="mt-1 max-w-xl text-slate">
          Save the jobs you want to apply for. Paste the text or upload the PDF, and compare your resumes against any of them later.
        </p>

        <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_1.4fr]">
          <form onSubmit={handleSave} className="h-fit space-y-4 rounded-2xl border border-line bg-white p-6">
            <h2 className="font-display text-xl font-bold">Add a job description</h2>
            <ErrorNote>{formError}</ErrorNote>
            <Field label="Job title" required maxLength={150} placeholder="Full Stack Developer"
              value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <Field label="Organization (optional)" maxLength={150} placeholder="Company name"
              value={form.organization} onChange={(e) => setForm({ ...form, organization: e.target.value })} />

            <div className="flex gap-1 rounded-lg bg-paper p-1">{tab("text", "Paste text")}{tab("pdf", "Upload PDF")}</div>

            {mode === "text" ? (
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">Job description</span>
                <textarea rows={8} maxLength={MAX_TEXT} placeholder="Paste the full job description here…"
                  value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })}
                  className="w-full rounded-lg border border-line bg-white px-3.5 py-2.5 placeholder:text-slate/50 hover:border-slate/40 focus:border-ink" />
                <span className="text-xs text-slate">{form.text.trim().length} / {MAX_TEXT} characters</span>
              </label>
            ) : (
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">PDF file (up to 5 MB)</span>
                <input key={fileKey} type="file" accept="application/pdf" onChange={chooseFile}
                  className="w-full rounded-lg border border-dashed border-slate/40 bg-paper p-3 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-ink file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-white" />
              </label>
            )}

            <button disabled={saving} className="w-full rounded-lg bg-ink px-4 py-3 font-semibold text-white hover:bg-ink-soft disabled:opacity-60">
              {saving ? "Saving…" : "Save job description"}
            </button>
          </form>

          <section>
            <ErrorNote>{loadError}</ErrorNote>
            {loading && <p className="text-slate">Loading your job descriptions…</p>}
            {!loading && !loadError && jds.length === 0 && (
              <div className="rounded-2xl border border-dashed border-slate/30 p-8">
                <p className="font-display text-lg font-bold">No job descriptions yet</p>
                <p className="mt-1 text-slate">Paste or upload your first one on the left.</p>
              </div>
            )}
            <ul className="space-y-4">
              {jds.map((j) => <JobCard key={j.id} jd={j} onChanged={load} />)}
            </ul>
          </section>
        </div>
      </main>
    </div>
  );
}
