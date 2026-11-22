import { useRef, useState } from "react";
import { api, openPdf } from "../lib/api";
import Field, { ErrorNote } from "./Field";

const MAX_BYTES = 5 * 1024 * 1024;

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  return bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const smallBtn = "rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:bg-paper disabled:opacity-60";

// One resume: shows details and offers view / new version / rename / delete.
export default function ResumeCard({ resume, onChanged }) {
  const fileInput = useRef(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(resume.name);
  const [role, setRole] = useState(resume.targetRole);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Run any action with shared busy/error handling
  async function run(action) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const current = resume.currentVersion;

  const viewPdf = () => run(() => openPdf(`/resumes/${resume.id}/versions/${resume.currentVersionNo}/file`));

  const saveRename = () =>
    run(async () => {
      await api(`/resumes/${resume.id}`, { method: "PATCH", body: { name, targetRole: role } });
      setEditing(false);
      await onChanged();
    });

  const remove = () =>
    run(async () => {
      await api(`/resumes/${resume.id}?confirm=true`, { method: "DELETE" });
      await onChanged();
    });

  function pickNewVersion(e) {
    const file = e.target.files[0];
    e.target.value = ""; // allow choosing the same file again later
    if (!file) return;
    if (file.size > MAX_BYTES) return setError("That PDF is larger than 5 MB.");
    run(async () => {
      const body = new FormData();
      body.append("file", file);
      await api(`/resumes/${resume.id}/versions`, { method: "POST", body });
      await onChanged();
    });
  }

  return (
    <li className="rounded-2xl border border-line bg-white p-5">
      {editing ? (
        <div className="space-y-3">
          <Field label="Resume name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          <Field label="Target role" value={role} maxLength={100} placeholder="Data Analyst" onChange={(e) => setRole(e.target.value)} />
          <div className="flex gap-2">
            <button onClick={saveRename} disabled={busy || !name.trim()} className="rounded-lg bg-ink px-4 py-1.5 text-sm font-semibold text-white hover:bg-ink-soft disabled:opacity-60">Save</button>
            <button onClick={() => { setEditing(false); setName(resume.name); setRole(resume.targetRole); }} className={smallBtn}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-display text-lg font-bold">{resume.name}</h3>
            <p className="text-sm text-slate">{resume.targetRole || "No target role set"}</p>
          </div>
          <span className="rounded-full bg-marigold/20 px-3 py-1 text-sm font-semibold">
            Version {resume.currentVersionNo}
          </span>
        </div>
      )}

      {current && !editing && (
        <p className="mt-3 text-sm text-slate">
          {current.originalFileName} &middot; {formatSize(current.fileSize)} &middot; uploaded {new Date(current.uploadedAt).toLocaleDateString()}
        </p>
      )}

      <div className="mt-4 space-y-3">
        <ErrorNote>{error}</ErrorNote>

        {confirmDelete ? (
          <div className="rounded-lg bg-red-50 p-3">
            <p className="text-sm text-red-800">
              Delete &ldquo;{resume.name}&rdquo; and all {resume.currentVersionNo} version{resume.currentVersionNo > 1 ? "s" : ""}? This can&rsquo;t be undone.
            </p>
            <div className="mt-2 flex gap-2">
              <button onClick={remove} disabled={busy} className="rounded-lg bg-red-600 px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60">Delete resume</button>
              <button onClick={() => setConfirmDelete(false)} className={smallBtn}>Keep it</button>
            </div>
          </div>
        ) : (
          !editing && (
            <div className="flex flex-wrap gap-2">
              <button onClick={viewPdf} disabled={busy} className={smallBtn}>View PDF</button>
              <button onClick={() => fileInput.current.click()} disabled={busy} className={smallBtn}>Upload new version</button>
              <button onClick={() => setEditing(true)} className={smallBtn}>Rename</button>
              <button onClick={() => setConfirmDelete(true)} className={`${smallBtn} text-red-700`}>Delete</button>
              <input ref={fileInput} type="file" accept="application/pdf" className="hidden" onChange={pickNewVersion} />
            </div>
          )
        )}
      </div>
    </li>
  );
}
