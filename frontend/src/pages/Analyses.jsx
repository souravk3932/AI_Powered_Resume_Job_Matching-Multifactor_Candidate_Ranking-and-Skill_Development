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

  async function compare(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data = await api("/analyses", { method: "POST", body: { resumeId, jdId } });
      setCurrent(data.analysis);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
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
                    <option key={r.id} value={r.id} disabled={!resumeReady(r)}>
                      {r.name} (v{r.currentVersionNo}){resumeReady(r) ? "" : " – analyse with AI first"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">Job description</span>
                <select className={selectCls} value={jdId} onChange={(e) => setJdId(e.target.value)} required>
                  <option value="">Choose a job…</option>
                  {jds.map((j) => (
                    <option key={j.id} value={j.id} disabled={!jdReady(j)}>
                      {j.title}{j.organization ? ` – ${j.organization}` : ""}{jdReady(j) ? "" : " – analyse with AI first"}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={busy || !resumeId || !jdId} className="w-full rounded-lg bg-ink px-4 py-3 font-semibold text-white hover:bg-ink-soft disabled:opacity-60">
                {busy ? "Comparing…" : "Compare skills"}
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
                        Required: {a.summary?.required?.matched ?? 0} of {a.summary?.required?.total ?? 0} matched &middot; {new Date(a.createdAt).toLocaleDateString()}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <section className="rounded-2xl border border-line bg-white p-6">
            {current ? <MatchResult analysis={current} /> : (
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
