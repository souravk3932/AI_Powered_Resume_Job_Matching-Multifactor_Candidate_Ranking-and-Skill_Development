import { useState } from "react";

// Shows the explainable score of ONE comparison: the overall number, how it was built, and every factor.

const STATUS = {
  evaluated: null,
  not_provided: { label: "Not provided", cls: "bg-marigold/30 text-ink", hint: "The job asks for this, but your resume gave no information. It is left out of the sum, not scored as zero." },
  not_applicable: { label: "Not applicable", cls: "bg-slate/10 text-slate", hint: "Neutral: nothing to judge here, and nothing counted against you." },
  not_available: { label: "Not available yet", cls: "bg-slate/10 text-slate", hint: "Needs a skill assessment you have not taken yet." },
};

function Bar({ value }) {
  return (
    <div className="h-2 w-full rounded-full bg-line">
      <div className="h-2 rounded-full bg-teal" style={{ width: `${Math.max(2, value)}%` }} />
    </div>
  );
}

function FactorRow({ f }) {
  const s = STATUS[f.status];
  return (
    <li className="rounded-lg border border-line bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{f.name}</p>
        {s ? <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>
           : <span className="text-sm font-semibold">{f.score.toFixed(1)} <span className="font-normal text-slate">/ 100</span></span>}
      </div>
      {f.status === "evaluated" ? (
        <>
          <div className="mt-2"><Bar value={f.score} /></div>
          <p className="mt-1.5 text-xs text-slate">
            Weight {f.weight}% &rarr; counts as {f.effective_weight}% &middot; adds <b className="text-ink">{f.contribution.toFixed(1)}</b> points
          </p>
        </>
      ) : <p className="mt-1 text-xs text-slate">{s.hint} (weight {f.weight}%)</p>}

      <details className="mt-1.5 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-ink">How this was calculated</summary>
        {f.steps.map((t, i) => <p key={i} className="mt-1 text-xs text-slate">{t}</p>)}
        {f.items.length > 0 && (
          <ul className="mt-2 space-y-1">
            {f.items.map((it, i) => (
              <li key={i} className="rounded bg-paper px-2 py-1 text-xs">
                <b>{it.label}</b> &middot; {it.points} points<span className="text-slate"> &middot; {it.detail}</span>
              </li>
            ))}
          </ul>
        )}
        {f.notes.map((n, i) => <p key={i} className="mt-1 text-xs font-medium text-ink">{n}</p>)}
      </details>
    </li>
  );
}

export default function ScorePanel({ analysis, roles, onRescore, busy, error }) {
  const snapshots = analysis.scoreSnapshots || [];
  const [picked, setPicked] = useState(null);       // which snapshot is on screen (default: the newest)
  const [role, setRole] = useState("");

  if (snapshots.length === 0) {
    return (
      <p className="rounded-lg bg-marigold/20 p-3 text-sm">
        No score is available for this comparison. Run a new comparison to get one.
      </p>
    );
  }
  const index = picked ?? snapshots.length - 1;
  const result = snapshots[index].result;
  const roleId = role || result.role_profile.id;

  return (
    <section className="space-y-4 rounded-2xl border border-line bg-paper p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-slate">Evidence fit for the <b>{result.role_profile.name}</b> role</p>
          <p className="font-display text-5xl font-bold">{result.overall ?? "–"}<span className="text-xl font-normal text-slate"> / 100</span></p>
        </div>
        <p className="max-w-xs text-sm text-slate">
          Based on <b>{Math.round(result.coverage * 100)}%</b> of the criteria that apply ({result.evidence_level} evidence).
          {result.not_provided.length > 0 && <> If the missing information ({result.not_provided.join(", ")}) counted as zero, the score would be <b>{result.lower_bound}</b>.</>}
        </p>
      </div>

      <p className="text-xs text-slate">{result.disclaimer} {result.formula}</p>

      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm font-medium" htmlFor="role">Score as</label>
        <select id="role" value={roleId} onChange={(e) => setRole(e.target.value)}
          className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm">
          {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <button disabled={busy || roleId === result.role_profile.id} onClick={() => { setPicked(null); onRescore(roleId); }}
          className="rounded-lg bg-ink px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-ink-soft disabled:opacity-60">
          {busy ? "Scoring…" : "Score with this role"}
        </button>
        <span className="text-xs text-slate">Same evidence, different weights. Each run is kept below.</span>
      </div>
      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <ul className="space-y-2">{result.factors.map((f) => <FactorRow key={f.id} f={f} />)}</ul>

      <details className="rounded-lg bg-white p-3 text-sm">
        <summary className="cursor-pointer font-medium">The sum, step by step</summary>
        <ul className="mt-2 space-y-0.5 text-xs text-slate">{result.calculation.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="mt-2 text-xs font-semibold">Overall = {result.overall}</p>
      </details>

      <p className="text-xs text-slate">Never used in the score: {result.not_used.join(", ")}.</p>

      {snapshots.length > 1 && (
        <div>
          <p className="text-sm font-semibold">Score history for this comparison</p>
          <ul className="mt-1 space-y-1">
            {snapshots.map((s, i) => (
              <li key={i}>
                <button onClick={() => setPicked(i)} className={`w-full rounded border px-2.5 py-1 text-left text-xs hover:bg-white ${i === index ? "border-ink bg-white" : "border-line"}`}>
                  <b>{s.result.overall ?? "–"}</b> &middot; {s.result.role_profile.name} &middot; {new Date(s.at).toLocaleString()}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
