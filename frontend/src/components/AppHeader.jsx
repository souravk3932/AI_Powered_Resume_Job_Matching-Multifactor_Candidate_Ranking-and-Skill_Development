import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

// Top bar shared by every logged-in page
const linkClass = ({ isActive }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-ink text-white" : "text-slate hover:bg-paper"}`;

export default function AppHeader() {
  const { student, logout } = useAuth();
  return (
    <header className="border-b border-line bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-marigold font-display font-bold text-ink">R</span>
            <span className="hidden font-display text-lg font-bold sm:block">ResumeFit</span>
          </div>
          <nav className="flex gap-1">
            <NavLink to="/dashboard" className={linkClass}>Profile</NavLink>
            <NavLink to="/resumes" className={linkClass}>Resumes</NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <span className="hidden text-sm text-slate md:block">{student.email}</span>
          <button onClick={logout} className="rounded-lg border border-line px-3.5 py-1.5 text-sm font-medium hover:bg-paper">
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}
