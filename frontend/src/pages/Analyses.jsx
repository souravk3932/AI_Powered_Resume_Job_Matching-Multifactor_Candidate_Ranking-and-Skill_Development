import { useCallback, useEffect, useState } from "react";
import AppHeader from "../components/AppHeader";
import { ErrorNote } from "../components/Field";
import MatchResult from "../components/MatchResult";
import { api } from "../lib/api";

const selectCls = "w-full rounded-lg border border-line bg-white px-3.5 py-2.5 hover:border-slate/40 focus:border-ink";

export default function Analyses() {
  const [resumes, setResumes] = useState([]);
  const [jds, setJds] = useState([]);
  const [history, setHistory] = useState([]);
  const [resumeId, setResumeId] = useState("");
  const [jdId, setJdId] = useState("");
  const [current, setCurrent] = useState(null); // the analysis being shown
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [roles, setRoles] = useState([]);       // role profiles for the "score as" chooser
  const [progress, setProgress] = useState("");   // what the Compare button is doing right now
  const [rescoring, setRescoring] = useState(false);
  const [rescoreError, setRescoreError] = useState("");

  const load = useCallback(async () => {
    try {
      const [r, j, h] = await Promise.all([api("/resumes"), api("/jds"), api("/analyses")]);
      setResumes(r.resumes);
      setJds(j.jds);
      setHistory(h.analyses);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api("/analyses/roles").then((d) => setRoles(d.roles)).catch(() => {}); }, []);

  // Score the same comparison again with another role's weights (adds a snapshot, keeps the old ones)
  async function rescore(roleProfile) {
    setRescoreError("");
    setRescoring(true);
    try {
      const data = await api(`/analyses/${current.id}/score`, { method: "POST", body: { roleProfile } });
      setCurrent(data.analysis);
      await load();
    } catch (err) {
      setRescoreError(err.message);
    } finally {
      setRescoring(false);
    }
  }

  // Get one document ready for comparing: read its text if that has not happened, then let the AI analyse it.
  // Each step says what it is doing, and a failure stops with the real reason.
  async function prepare(base, label, textDone, profileDone) {
    if (!textDone) {
      setProgress(`Reading the text of ${label}…`);
      const read = (await api(`${base}/extract`, { method: "POST" })).extraction;
      if (read.status !== "done") throw new Error(read.error || `Could not read the text of ${label}.`);
    }
    if (!profileDone) {
      setProgress(`The AI is reading ${label} (about 10 seconds)…`);
      const analysed = (await api(`${base}/profile`, { method: "POST" })).profile;
      if (analysed.status !== "done") throw new Error(analysed.error || `The AI could not read ${label}.`);
    }
  }

  async function compare(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const resume = resumes.find((r) => r.id === resumeId);
      const job = jds.find((j) => j.id === jdId);
      // 1. Make sure both documents are ready (this is what used to be left to the student)
      await prepare(`/resumes/${resume.id}/versions/${resume.currentVersionNo}`, `your resume “${resume.name}”`,
        resume.currentVersion.extraction.status === "done", resumeReady(resume));
      await prepare(`/jds/${job.id}`, `the job “${job.title}”`, job.extraction.status === "done", jdReady(job));
      // 2. Compare and score
      setProgress("Comparing skills and scoring…");
      const data = await api("/analyses", { method: "POST", body: { resumeId, jdId } });
      setCurrent(data.analysis);
      await load();
    } catch (err) {
      setError(err.message);
      await load(); // whatever did get prepared is kept, so the next try starts further along
    } finally {
      setBusy(false);
      setProgress("");
    }
  }

  async function open(id) {
    setError("");
    try {
      setCurrent((await api(`/analyses/${id}`)).analysis);
    } catch (err) {
      setError(err.message);
    }
  }

  const resumeReady = (r) => r.currentVersion?.profile?.status === "done";
  const jdReady = (j) => j.profile?.status === "done";
  const noData = resumes.length === 0 || jds.length === 0;

  return (
    <div className="min-h-screen">
      <AppHeader />
      <main className="mx-auto max-w-5xl px-6 py-10">
        <h1 className="font-display text-3xl font-bold sm:text-4xl">Compare a resume with a job</h1>
        <p className="mt-1 max-w-xl text-slate">
          Pick one resume and one job description. Every comparison is saved, so you can look back later.
        </p>

        <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_1.6fr]">
          <div className="space-y-6">
            <form onSubmit={compare} className="space-y-4 rounded-2xl border border-line bg-white p-6">
              <h2 className="font-display text-xl font-bold">New comparison</h2>
              <ErrorNote>{error}</ErrorNote>
              {noData && <p className="text-sm text-slate">Add at least one resume and one job description first (see Resumes and Jobs).</p>}
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">Resume</span>
                <select className={selectCls} value={resumeId} onChange={(e) => setResumeId(e.target.value)} required>
                  <option value="">Choose a resume…</option>
                  {resumes.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} (v{r.currentVersionNo}){resumeReady(r) ? "" : " – the AI will read it first"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">Job description</span>
                <select className={selectCls} value={jdId} onChange={(e) => setJdId(e.target.value)} required>
                  <option value="">Choose a job…</option>
                  {jds.map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.title}{j.organization ? ` – ${j.organization}` : ""}{jdReady(j) ? "" : " – the AI will read it first"}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={busy || !resumeId || !jdId} className="w-full rounded-lg bg-ink px-4 py-3 font-semibold text-white hover:bg-ink-soft disabled:opacity-60">
                {busy ? (progress || "Comparing…") : "Compare skills"}
              </button>
            </form>

            <section>
              <h2 className="font-display text-lg font-bold">Earlier comparisons</h2>
              {history.length === 0 && <p className="mt-2 text-sm text-slate">Nothing yet.</p>}
              <ul className="mt-2 space-y-2">
                {history.map((a) => (
                  <li key={a.id}>
                    <button onClick={() => open(a.id)}
                      className={`w-full rounded-lg border p-3 text-left text-sm hover:bg-paper ${current?.id === a.id ? "border-ink" : "border-line bg-white"}`}>
                      <p className="font-semibold">{a.resumeName} (v{a.versionNo}) vs {a.jobTitle}</p>
                      <p className="text-xs text-slate">
                        {a.latestScore?.overall != null && <><b>Score {a.latestScore.overall}</b> &middot; </>}
                        Required: {a.summary?.required?.matched ?? 0} of {a.summary?.required?.total ?? 0} matched &middot; {new Date(a.createdAt).toLocaleDateString()}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <section className="rounded-2xl border border-line bg-white p-6">
            {current ? <MatchResult key={current.id} analysis={current} roles={roles} onRescore={rescore} rescoring={rescoring} rescoreError={rescoreError} /> : (
              <div>
                <p className="font-display text-lg font-bold">No comparison selected</p>
                <p className="mt-1 text-slate">Run a new comparison, or open an earlier one from the list.</p>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
