// A labelled input used by every form. Label is real text (good for accessibility).
export default function Field({ label, as = "input", ...props }) {
  const Tag = as;
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      <Tag
        {...props}
        className="w-full rounded-lg border border-line bg-white px-3.5 py-2.5 text-ink placeholder:text-slate/50 transition-colors hover:border-slate/40 focus:border-ink"
      />
    </label>
  );
}

export function PrimaryButton({ busy, children, ...props }) {
  return (
    <button
      {...props}
      disabled={busy}
      className="w-full rounded-lg bg-ink px-4 py-3 font-semibold text-white transition-colors hover:bg-ink-soft disabled:opacity-60"
    >
      {children}
    </button>
  );
}

export function ErrorNote({ children }) {
  if (!children) return null;
  return <p role="alert" className="rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-700">{children}</p>;
}
