import { useState } from "react";
import Field, { ErrorNote } from "../components/Field";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";

const PROFILE_KEYS = ["phone", "college", "degree", "graduationYear", "careerGoal", "about"];

// What the student will be able to do next (built in later phases)
const COMING = [
  { title: "Resumes", text: "Upload several versions, one per role." },
  { title: "Job descriptions", text: "Paste or upload the job you want." },
  { title: "Analyses", text: "Scores, skill gaps and your roadmap." },
];

export default function Dashboard() {
  const { student, setStudent, logout } = useAuth();
  const [name, setName] = useState(student.name);
  const [profile, setProfile] = useState({ ...student.profile });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Profile completeness: how many optional fields are filled in
  const filled = PROFILE_KEYS.filter((k) => String(profile[k] ?? "").trim() !== "").length;
  const percent = Math.round((filled / PROFILE_KEYS.length) * 100);
  const set = (key) => (e) => setProfile({ ...profile, [key]: e.target.value });

  async function handleSave(e) {
    e.preventDefault();
    setMessage("");
    setError("");
    setSaving(true);
    try {
      const body = { name, profile: { ...profile, graduationYear: profile.graduationYear || undefined } };
      const data = await api("/profile", { method: "PUT", body });
      setStudent({ ...student, ...data.student });
      setMessage("Profile saved.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-marigold font-display font-bold text-ink">R</span>
            <span className="font-display text-lg font-bold">ResumeFit</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden text-sm text-slate sm:block">{student.email}</span>
            <button onClick={logout} className="rounded-lg border border-line px-3.5 py-1.5 text-sm font-medium hover:bg-paper">
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <h1 className="font-display text-3xl font-bold sm:text-4xl">Hi, {student.name.split(" ")[0]}.</h1>
            <p className="mt-1 text-slate">Let&rsquo;s set up your profile first. Resumes come next.</p>
          </div>
          <div className="w-full max-w-xs">
            <div className="flex justify-between text-sm">
              <span className="font-medium">Profile complete</span>
              <span className="text-slate">{percent}%</span>
            </div>
            <div className="mt-1.5 h-2 rounded-full bg-line">
              <div className="h-2 rounded-full bg-teal transition-all duration-500" style={{ width: `${percent}%` }} />
            </div>
          </div>
        </div>

        <div className="mt-10 grid gap-8 lg:grid-cols-[1.4fr_1fr]">
          <form onSubmit={handleSave} className="space-y-4 rounded-2xl border border-line bg-white p-6 sm:p-8">
            <h2 className="font-display text-xl font-bold">Your profile</h2>
            {message && <p role="status" className="rounded-lg bg-teal/10 px-3.5 py-2.5 text-sm text-teal">{message}</p>}
            <ErrorNote>{error}</ErrorNote>
            <Field label="Full name" value={name} maxLength={100} required onChange={(e) => setName(e.target.value)} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Phone" value={profile.phone ?? ""} onChange={set("phone")} maxLength={20} />
              <Field label="Graduation year" type="number" value={profile.graduationYear ?? ""} onChange={set("graduationYear")} />
            </div>
            <Field label="College or university" value={profile.college ?? ""} onChange={set("college")} />
            <Field label="Degree" value={profile.degree ?? ""} onChange={set("degree")} placeholder="B.Tech, Computer Science" />
            <Field label="Career goal" value={profile.careerGoal ?? ""} onChange={set("careerGoal")} placeholder="Full Stack Developer" />
            <Field label="About you" as="textarea" rows={3} maxLength={1000} value={profile.about ?? ""} onChange={set("about")} />
            <button disabled={saving} className="rounded-lg bg-ink px-5 py-2.5 font-semibold text-white hover:bg-ink-soft disabled:opacity-60">
              {saving ? "Saving…" : "Save profile"}
            </button>
          </form>

          <aside>
            <h2 className="font-display text-xl font-bold">Coming up</h2>
            <p className="mt-1 text-sm text-slate">These unlock as we build the next phases.</p>
            <ul className="mt-4 space-y-3">
              {COMING.map((item) => (
                <li key={item.title} className="rounded-xl border border-dashed border-slate/30 p-4">
                  <p className="font-semibold">{item.title}</p>
                  <p className="text-sm text-slate">{item.text}</p>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      </main>
    </div>
  );
}
