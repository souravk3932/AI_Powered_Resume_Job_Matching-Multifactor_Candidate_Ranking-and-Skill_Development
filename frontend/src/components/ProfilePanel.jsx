import { useState } from "react";
import { api } from "../lib/api";
import { ErrorNote } from "./Field";

const smallBtn = "rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:bg-paper disabled:opacity-60";

const join = (...parts) => parts.filter(Boolean).join(" · ");

// Everything that differs between a resume and a job description lives here
const KINDS = {
  resume: {
    source: "your resume",
    chips: ["technical_skills", "soft_skills"],
    labels: {
      technical_skills: "Technical skills", soft_skills: "Soft skills", education: "Education",
      experience: "Experience", projects: "Projects", certifications: "Certifications",
      achievements: "Achievements and leadership", funding: "Grants and funding",
    },
    // How to show one item: a title line and a details line
    show: {
      education: (i) => ({ title: join(i.degree, i.field_of_study) || i.institution || "Education", meta: join(i.institution, i.year) }),
      experience: (i) => ({ title: join(i.title, i.organization && `at ${i.organization}`) || "Experience", meta: join(i.kind, i.duration), list: i.responsibilities }),
      projects: (i) => ({ title: i.title, meta: join(i.technologies.join(", "), i.role, i.outcome), links: i.links }),
      certifications: (i) => ({ title: i.name, meta: join(i.issuer, i.date) }),
      achievements: (i) => ({ title: i.title, meta: join(i.kind, i.description) }),
      funding: (i) => ({ title: i.description, meta: join(i.source, i.amount_text, i.purpose, i.candidate_role, i.outcome) }),
    },
  },
  jd: {
    source: "the job description",
    chips: ["required_skills", "preferred_skills", "soft_skills", "competencies"],
    labels: {
      required_skills: "Required skills", preferred_skills: "Preferred skills", soft_skills: "Soft skills",
      competencies: "Role competencies", education_requirements: "Education asked for",
      experience_requirements: "Experience asked for", responsibilities: "Responsibilities", certifications: "Certifications",
    },
    show: {
      education_requirements: (i) => ({ title: i.text }),
      experience_requirements: (i) => ({ title: i.text, meta: i.years && `Years: ${i.years}` }),
      responsibilities: (i) => ({ title: i.text }),
      certifications: (i) => ({ title: i.name, meta: i.required ? "Required" : "Optional" }),
    },
  },
};

function StatusBadge({ item, source }) {
  return item.status === "supported"
    ? <span className="rounded-full bg-teal/10 px-2 py-0.5 text-xs font-semibold text-teal">Found in {source}</span>
    : <span className="rounded-full bg-marigold/30 px-2 py-0.5 text-xs font-semibold">Needs review</span>;
}

function Quote({ item, source }) {
  return (
    <p className="mt-1 text-xs text-slate">
      From {source}: &ldquo;{item.quote}&rdquo;
      {item.status !== "supported" && <span className="ml-1 font-medium text-ink">{item.note} Please check it.</span>}
    </p>
  );
}

// Shows what the AI understood from one resume version or one job description (kind = "resume" | "jd")
export default function ProfilePanel({ kind = "resume", path, textReady, profile, onChanged }) {
  const { labels, show, chips, source } = KINDS[kind];
  const order = Object.keys(labels);
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const status = profile?.status || "not_started";

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

  const analyse = () =>
    run(async () => {
      await api(`${path}/profile`, { method: "POST" });
      setOpen(false);
      setData(null);
      await onChanged();
    });

  const toggle = () =>
    open
      ? setOpen(false)
      : run(async () => {
          setData((await api(`${path}/profile`)).profile.data);
          setOpen(true);
        });

  const hidden = profile?.redactions || {};
  const hiddenText = [
    hidden.email && `${hidden.email} email`, hidden.phone && `${hidden.phone} phone number`,
    hidden.link && `${hidden.link} link${hidden.link > 1 ? "s" : ""}`, hidden.name && "your name",
  ].filter(Boolean).join(", ");

  return (
    <div className="mt-3 rounded-xl bg-paper p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm">
          <span className="font-semibold">AI profile</span>
          {status === "done" && (
            <span className="text-slate">
              {" "}&middot; {Object.values(profile.counts).reduce((a, b) => a + b, 0)} items
              {profile.needsReview > 0 && <b className="text-ink"> &middot; {profile.needsReview} need review</b>}
            </span>
          )}
          {status === "not_started" && <span className="text-slate"> &middot; not analysed yet</span>}
          {status === "failed" && <span className="font-semibold text-red-700"> &middot; failed</span>}
        </p>
        <div className="flex gap-2">
          {status === "done" && <button onClick={toggle} disabled={busy} className={smallBtn}>{open ? "Hide profile" : "View profile"}</button>}
          <button onClick={analyse} disabled={busy || !textReady} className={smallBtn}
            title={textReady ? "" : "Read the text first"}>
            {busy ? "Analysing…" : status === "not_started" ? "Analyse with AI" : "Analyse again"}
          </button>
        </div>
      </div>

      {!textReady && status === "not_started" && <p className="mt-2 text-sm text-slate">Read the text above first, then analyse it.</p>}
      {status === "failed" && profile.error && <p className="mt-2 text-sm text-red-700">{profile.error}</p>}
      {status === "done" && hiddenText && (
        <p className="mt-2 text-xs text-slate">Hidden before sending to the AI: {hiddenText}.</p>
      )}
      {status === "done" && profile.warnings.map((w) => (
        <p key={w} className="mt-2 rounded-md bg-marigold/20 px-2.5 py-1.5 text-sm">{w}</p>
      ))}
      <div className="mt-2"><ErrorNote>{error}</ErrorNote></div>

      {open && data && (
        <div className="mt-3 space-y-4">
          <p className="text-sm text-slate">
            This is what an AI read from {kind === "jd" ? "the job description" : "your text"}. It can make mistakes, so every item shows the exact words it used.
            Other details are the AI&rsquo;s reading of those words. Nothing here is a score.
          </p>
          {data.job_title && <p className="text-sm">Job title written in the text: <b>{data.job_title}</b></p>}
          {order.filter((c) => (data[c] || []).length > 0).map((category) => (
            <section key={category}>
              <h4 className="text-sm font-semibold">{labels[category]} <span className="font-normal text-slate">({data[category].length})</span></h4>

              {category === "funding" && (
                <p className="mt-1 text-xs text-slate">Funding is never scored by amount alone. Later, relevance, evidence and your own role are what count.</p>
              )}

              {chips.includes(category) ? (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {data[category].map((s, i) => (
                    <li key={i} title={`From ${source}: "${s.quote}"`}
                      className={`rounded-full border px-2.5 py-1 text-sm ${s.status === "supported" ? "border-teal/40 bg-white" : "border-marigold bg-marigold/20"}`}>
                      {s.name}{s.status !== "supported" && " ?"}
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="mt-2 space-y-2">
                  {data[category].map((item, i) => {
                    const v = show[category](item);
                    return (
                      <li key={i} className="rounded-lg border border-line bg-white p-3">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <p className="text-sm font-semibold">{v.title}</p>
                          <StatusBadge item={item} source={source} />
                        </div>
                        {v.meta && <p className="mt-0.5 text-sm text-slate">{v.meta}</p>}
                        {v.list?.length > 0 && (
                          <ul className="mt-1 list-disc pl-5 text-sm text-slate">{v.list.map((r, k) => <li key={k}>{r}</li>)}</ul>
                        )}
                        {v.links?.length > 0 && <p className="mt-1 break-all text-sm text-slate">Links: {v.links.join(", ")}</p>}
                        <Quote item={item} source={source} />
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
