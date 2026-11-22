import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken } from "../lib/api";

// AuthContext = one shared place that knows "who is logged in".
// Any page can read it with useAuth().
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [student, setStudent] = useState(null);
  const [loading, setLoading] = useState(!!getToken()); // only wait if a token exists

  // On page load: if we have a saved token, ask the backend who it belongs to
  useEffect(() => {
    if (!getToken()) return;
    api("/profile")
      .then((d) => setStudent(d.student))
      .catch(() => localStorage.removeItem("token")) // token expired/invalid
      .finally(() => setLoading(false));
  }, []);

  async function authenticate(path, body) {
    const data = await api(path, { method: "POST", body });
    localStorage.setItem("token", data.token);
    const profile = await api("/profile");
    setStudent(profile.student);
  }

  const login = (email, password) => authenticate("/auth/login", { email, password });
  const register = (name, email, password) => authenticate("/auth/register", { name, email, password });

  function logout() {
    localStorage.removeItem("token");
    setStudent(null);
  }

  return (
    <AuthContext.Provider value={{ student, setStudent, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
