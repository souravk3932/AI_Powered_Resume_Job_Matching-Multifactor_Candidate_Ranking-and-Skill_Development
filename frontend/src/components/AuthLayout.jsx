// Shared split layout for Login and Register.
// Left: a worked example of how a score is built (the idea of the whole project).
// Right: the form (passed in as children).

// Example numbers only - clearly labelled as an example on screen.
const EXAMPLE = [
  { label: "Technical skills", score: 85, weight: 25 },
  { label: "Projects", score: 70, weight: 15 },
  { label: "Experience", score: 55, weight: 15 },
  { label: "Education", score: 90, weight: 10 },
  { label: "Soft skills", score: 65, weight: 10 },
];

function Logo({ dark }) {
  return (
    <div className="flex items-center gap-2">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-marigold font-display font-bold text-ink">R</span>
      <span className={`font-display text-lg font-bold ${dark ? "text-white" : "text-ink"}`}>ResumeFit</span>
    </div>
  );
}

export default function AuthLayout({ title, subtitle, children, footer }) {
  const total = EXAMPLE.reduce((sum, f) => sum + (f.score * f.weight) / 100, 0);
  const maxPoints = EXAMPLE.reduce((sum, f) => sum + f.weight, 0); // best possible from these factors

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="hidden bg-ink p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <Logo dark />

        <div className="max-w-md">
          <h2 className="font-display text-4xl font-bold leading-tight">
            See exactly why your resume scores the way it does.
          </h2>
          <p className="mt-3 text-white/70">
            Every factor has a score and a weight. No black box, and no guesses presented as facts.
          </p>

          <div className="mt-8 rounded-2xl bg-ink-soft p-6">
            <p className="text-sm text-white/60">Example for a Software Developer role</p>
            <ul className="mt-4 space-y-4">
              {EXAMPLE.map((f, i) => (
                <li key={f.label}>
                  <div className="flex justify-between text-sm">
                    <span>{f.label}</span>
                    <span className="text-white/60">{f.score} × {f.weight}% = {((f.score * f.weight) / 100).toFixed(1)}</span>
                  </div>
                  <div className="mt-1.5 h-2 rounded-full bg-white/10">
                    <div className="bar-fill h-2 rounded-full bg-marigold"
                      style={{ width: `${f.score}%`, animationDelay: `${i * 90}ms` }} />
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-5 border-t border-white/10 pt-4 text-sm text-white/70">
              Score so far from these five factors: <b className="text-marigold">{total.toFixed(1)}</b> of {maxPoints} possible points
            </p>
          </div>
        </div>

        <p className="text-sm text-white/50">A guide for your career, not a hiring decision.</p>
      </section>

      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-10 lg:hidden"><Logo /></div>
          <h1 className="font-display text-3xl font-bold">{title}</h1>
          <p className="mt-2 text-slate">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <p className="mt-6 text-sm text-slate">{footer}</p>
        </div>
      </section>
    </main>
  );
}
