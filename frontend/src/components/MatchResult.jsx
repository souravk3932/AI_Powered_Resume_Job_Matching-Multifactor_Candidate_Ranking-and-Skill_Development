// Shows ONE analysis: how a resume's skills line up with a job description's requirements.

const GROUPS = [
  ["required", "Required skills"],
  ["preferred", "Preferred skills"],
  ["soft", "Soft skills"],
];

const STATUS = {
  matched: { label: "Matched", cls: "bg-teal/10 text-teal" },
  partial: { label: "Partly matched", cls: "bg-marigold/30 text-ink" },
  missing: { label: "Not found", cls: "bg-slate/10 text-slate" },
};

const METHOD = {
  exact: "same skill", alias: "same skill, written differently", implied: "included in a skill you have",
  broader: "you have the general skill", family: "similar skill", semantic: "similar meaning (suggestion)", none: "",
};

const SUPPORT = { demonstrated: "Shown in your work", certified: "Certificate", listed: "Listed only" };

function Row({ item }) {
  const s = STATUS[item.status];
  return (
    <li className="rounded-lg border border-line bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{item.requirement}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          {item.support && <span className="rounded-full border border-line px-2 py-0.5 text-xs text-slate">{SUPPORT[item.support]}</span>}
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>
        </div>
      </div>
      <p className="mt-1 text-sm text-slate">{item.reason}</p>
      {item.method !== "none" && (
        <p className="mt-0.5 text-xs text-slate">
          How: {METHOD[item.method]} &middot; confidence: {item.confidence}
          {item.similarity !== undefined && <> &middot; similarity {item.similarity}</>}
        </p>
      )}
      {item.evidence.length > 0 && (
        <details className="mt-1.5 text-sm">
          <summary className="cursor-pointer text-xs font-medium text-ink">Evidence from your resume</summary>
          <ul className="mt-1 space-y-1 text-xs text-slate">
            {item.evidence.map((e, i) => <li key={i}><b>{e.source}</b>: &ldquo;{e.text}&rdquo;</li>)}
          </ul>
        </details>
      )}
      <details className="mt-1 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-ink">What the job description says</summary>
        <p className="mt-1 text-xs text-slate">&ldquo;{item.jd_quote}&rdquo;</p>
      </details>
    </li>
  );
}

import ScorePanel from "./ScorePanel";

export default function MatchResult({ analysis, roles = [], onRescore, rescoring, rescoreError }) {
  const skills = analysis.skillMatch?.skills || [];
  const notUsed = analysis.skillMatch?.not_used || {};
  const unverified = [...(notUsed.resume_items_needing_review || []), ...(notUsed.job_items_needing_review || [])];

  return (
    <div className="space-y-5">
      <div>
        <h3 className="font-display text-xl font-bold">
          {analysis.resumeName} <span className="font-normal text-slate">(version {analysis.versionNo})</span> vs {analysis.jobTitle}
        </h3>
        <p className="text-sm text-slate">
          {analysis.organization && `${analysis.organization} · `}run on {new Date(analysis.createdAt).toLocaleString()}
        </p>
      </div>

      <ScorePanel analysis={analysis} roles={roles} onRescore={onRescore} busy={rescoring} error={rescoreError} />

      <h3 className="font-display text-lg font-bold">Skill match</h3>
      <div className="grid gap-2 sm:grid-cols-3">
        {GROUPS.map(([key, label]) => {
          const c = analysis.summary?.[key] || { total: 0, matched: 0, partial: 0, missing: 0 };
          return (
            <div key={key} className="rounded-xl bg-paper p-3">
              <p className="text-sm font-semibold">{label}</p>
              <p className="text-2xl font-bold">{c.matched}<span className="text-base font-normal text-slate"> of {c.total} matched</span></p>
              <p className="text-xs text-slate">{c.partial} partly &middot; {c.missing} not found</p>
            </div>
          );
        })}
      </div>

      <p className="rounded-lg bg-paper p-3 text-sm text-slate">
        This compares <b>skills only</b>. It is not a score and not a prediction of being hired. &ldquo;Not found&rdquo; means not found in the
        text we could read from your resume. It does not mean you lack the skill, so add it to your resume if you have it.
      </p>

      {analysis.warnings?.map((w) => <p key={w} className="rounded-md bg-marigold/20 px-3 py-2 text-sm">{w}</p>)}
      {unverified.length > 0 && (
        <p className="text-sm text-slate">Not used because they could not be verified in the text: {unverified.join(", ")}.</p>
      )}

      {GROUPS.map(([key, label]) => {
        const items = skills.filter((s) => s.importance === key);
        if (items.length === 0) return null;
        return (
          <section key={key}>
            <h4 className="font-semibold">{label} <span className="font-normal text-slate">({items.length})</span></h4>
            <ul className="mt-2 space-y-2">{items.map((s) => <Row key={s.requirement} item={s} />)}</ul>
          </section>
        );
      })}
      {skills.length === 0 && <p className="text-slate">The job description had no verified skill requirements to compare.</p>}

      <p className="text-xs text-slate">
        Engine {analysis.engineVersion}{analysis.embeddingModel ? ` · meaning model ${analysis.embeddingModel}` : ""}.
      </p>
    </div>
  );
}
