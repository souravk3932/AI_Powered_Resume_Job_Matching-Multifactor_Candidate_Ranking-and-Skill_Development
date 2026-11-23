import { useState } from "react";
import { api } from "../lib/api";
import { ErrorNote } from "./Field";

const smallBtn = "rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:bg-paper disabled:opacity-60";

// Plain-English names for our standard section names
const LABELS = {
  preamble: "Top of the document", summary: "Summary", education: "Education", experience: "Experience",
  projects: "Projects", skills: "Skills", certifications: "Certifications", achievements: "Achievements",
  leadership: "Leadership", funding: "Grants and funding", publications: "Publications",
  about: "About", responsibilities: "Responsibilities", requirements: "Requirements",
  preferred: "Preferred", benefits: "Benefits",
};
const label = (name) => LABELS[name] || name;

// Shows "text reading" status for a resume version or a job description.
// path: the backend address of the thing, e.g. "/resumes/ID/versions/1" or "/jds/ID"
export default function ExtractionPanel({ path, extraction, onChanged }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const status = extraction?.status || "not_started";

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

  const readAgain = () =>
    run(async () => {
      await api(`${path}/extract`, { method: "POST" });
      setOpen(false);
      setDetail(null);
      await onChanged();
    });

  const toggle = () =>
    open
      ? setOpen(false)
      : run(async () => {
          setDetail((await api(`${path}/extraction`)).extraction);
          setOpen(true);
        });

  return (
    <div className="mt-4 rounded-xl bg-paper p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm">
          {status === "done" && (
            <>
              <span className="font-semibold text-teal">Text read</span>
              <span className="text-slate">
                {" "}&middot; {extraction.charCount.toLocaleString()} characters
                {extraction.pageCount > 0 && <>, {extraction.pagesRead} of {extraction.pageCount} page{extraction.pageCount > 1 ? "s" : ""}</>}
              </span>
            </>
          )}
          {status === "failed" && <span className="font-semibold text-red-700">Could not read the text</span>}
          {status === "not_started" && <span className="text-slate">Text not read yet</span>}
        </p>
        <div className="flex gap-2">
          {status === "done" && <button onClick={toggle} disabled={busy} className={smallBtn}>{open ? "Hide text" : "View extracted text"}</button>}
          <button onClick={readAgain} disabled={busy} className={smallBtn}>
            {busy ? "Working…" : status === "not_started" ? "Read text" : "Read again"}
          </button>
        </div>
      </div>

      {status === "failed" && extraction.error && <p className="mt-2 text-sm text-red-700">{extraction.error}</p>}
      {status === "done" && extraction.warnings.map((w) => (
        <p key={w} className="mt-2 rounded-md bg-marigold/20 px-2.5 py-1.5 text-sm">{w}</p>
      ))}
      <div className="mt-2"><ErrorNote>{error}</ErrorNote></div>

      {open && detail && (
        <div className="mt-3 space-y-3">
          {detail.expectedNotFound.length > 0 && (
            <p className="text-sm text-slate">
              Headings not found in this document: {detail.expectedNotFound.map(label).join(", ")}.
              This only describes the document. It does not mean anything is missing from you.
            </p>
          )}
          {detail.sections.length === 0 && <p className="text-sm text-slate">No text was found.</p>}
          {detail.sections.map((s, i) => (
            <section key={i} className="rounded-lg border border-line bg-white p-3">
              <h4 className="text-sm font-semibold">
                {label(s.name)}
                {s.heading && <span className="font-normal text-slate"> &middot; written as &ldquo;{s.heading}&rdquo;</span>}
              </h4>
              <p className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-sm text-slate">{s.text}</p>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
