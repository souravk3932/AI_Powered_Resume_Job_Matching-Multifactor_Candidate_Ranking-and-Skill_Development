import { useState } from "react";
import { api, openPdf } from "../lib/api";
import ExtractionPanel from "./ExtractionPanel";
import ProfilePanel from "./ProfilePanel";
import Field, { ErrorNote } from "./Field";

const smallBtn = "rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:bg-paper disabled:opacity-60";

// One saved job description: shows details and offers read / view PDF / rename / delete.
export default function JobCard({ jd, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(jd.title);
  const [org, setOrg] = useState(jd.organization);
  const [fullText, setFullText] = useState(null); // loaded only when the student asks
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

  const toggleText = () =>
    fullText !== null
      ? setFullText(null)
      : run(async () => setFullText((await api(`/jds/${jd.id}`)).jd.text));

  const saveRename = () =>
    run(async () => {
      await api(`/jds/${jd.id}`, { method: "PATCH", body: { title, organization: org } });
      setEditing(false);
      await onChanged();
    });

  const remove = () =>
    run(async () => {
      await api(`/jds/${jd.id}?confirm=true`, { method: "DELETE" });
      await onChanged();
    });

  const isPdf = jd.source === "pdf";

  return (
    <li className="rounded-2xl border border-line bg-white p-5">
      {editing ? (
        <div className="space-y-3">
          <Field label="Job title" value={title} maxLength={150} onChange={(e) => setTitle(e.target.value)} />
          <Field label="Organization (optional)" value={org} maxLength={150} onChange={(e) => setOrg(e.target.value)} />
          <div className="flex gap-2">
            <button onClick={saveRename} disabled={busy || !title.trim()} className="rounded-lg bg-ink px-4 py-1.5 text-sm font-semibold text-white hover:bg-ink-soft disabled:opacity-60">Save</button>
            <button onClick={() => { setEditing(false); setTitle(jd.title); setOrg(jd.organization); }} className={smallBtn}>Cancel</button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-display text-lg font-bold">{jd.title}</h3>
              <p className="text-sm text-slate">{jd.organization || "No organization added"}</p>
            </div>
            <span className="rounded-full bg-marigold/20 px-3 py-1 text-sm font-semibold">
              {isPdf ? "PDF" : "Pasted text"}
            </span>
          </div>

          {isPdf ? (
            <p className="mt-3 text-sm text-slate">
              {jd.originalFileName} &middot; saved {new Date(jd.createdAt).toLocaleDateString()}
            </p>
          ) : (
            <p className="mt-3 whitespace-pre-wrap text-sm text-slate">
              {fullText ?? (jd.preview.length >= 200 ? `${jd.preview}…` : jd.preview)}
            </p>
          )}
        </>
      )}

      {!editing && <ExtractionPanel path={`/jds/${jd.id}`} extraction={jd.extraction} onChanged={onChanged} />}
      {!editing && (
        <ProfilePanel kind="jd" path={`/jds/${jd.id}`} textReady={jd.extraction.status === "done"}
          profile={jd.profile} onChanged={onChanged} />
      )}

      <div className="mt-4 space-y-3">
        <ErrorNote>{error}</ErrorNote>
        {confirmDelete ? (
          <div className="rounded-lg bg-red-50 p-3">
            <p className="text-sm text-red-800">Delete &ldquo;{jd.title}&rdquo;? This can&rsquo;t be undone.</p>
            <div className="mt-2 flex gap-2">
              <button onClick={remove} disabled={busy} className="rounded-lg bg-red-600 px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60">Delete job description</button>
              <button onClick={() => setConfirmDelete(false)} className={smallBtn}>Keep it</button>
            </div>
          </div>
        ) : (
          !editing && (
            <div className="flex flex-wrap gap-2">
              {isPdf ? (
                <button onClick={() => run(() => openPdf(`/jds/${jd.id}/file`))} disabled={busy} className={smallBtn}>View PDF</button>
              ) : (
                <button onClick={toggleText} disabled={busy} className={smallBtn}>{fullText !== null ? "Show less" : "Read full text"}</button>
              )}
              <button onClick={() => setEditing(true)} className={smallBtn}>Rename</button>
              <button onClick={() => setConfirmDelete(true)} className={`${smallBtn} text-red-700`}>Delete</button>
            </div>
          )
        )}
      </div>
    </li>
  );
}
