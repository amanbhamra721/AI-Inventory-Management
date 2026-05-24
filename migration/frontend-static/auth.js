/**
 * auth.js — token-based auth module for GitHub Pages frontend.
 *
 * Stores the JWT in localStorage (never in a cookie).
 * All protected API calls attach the token as Authorization: Bearer <token>.
 *
 * Usage:
 *   Auth.login(phone, password)  → { ok: true } | { ok: false, error: "..." }
 *   Auth.logout()
 *   Auth.isLoggedIn()            → boolean
 *   Auth.getPhone()              → "9112345678" | null
 *   Auth.apiFetch(path, opts)    → fetch with token attached, redirects on 401
 */
const Auth = (() => {
  const TOKEN_KEY = "koshak_token";
  const PHONE_KEY = "koshak_phone";
  const base = () => window.APP_CONFIG?.apiBaseUrl || "";

  function save(token, phone) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(PHONE_KEY, phone);
  }

  function clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(PHONE_KEY);
  }

  async function login(phone, password) {
    try {
      const resp = await fetch(`${base()}/api/auth/login`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ phone, password }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        return { ok: false, error: err.detail || "Login failed. Please try again." };
      }

      const data = await resp.json();
      save(data.access_token, data.phone);
      return { ok: true };
    } catch {
      return { ok: false, error: "Cannot reach server. Check your connection." };
    }
  }

  function logout() {
    clear();
    window.location.replace("login.html");
  }

  function isLoggedIn() {
    return !!localStorage.getItem(TOKEN_KEY);
  }

  function getPhone() {
    return localStorage.getItem(PHONE_KEY);
  }

  /**
   * Wrapper around fetch that:
   *  1. Attaches Authorization header automatically.
   *  2. Redirects to login.html on 401.
   */
  async function apiFetch(path, opts = {}) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = { ...(opts.headers || {}), Authorization: `Bearer ${token}` };
    const resp = await fetch(`${base()}${path}`, { ...opts, headers });
    if (resp.status === 401) {
      clear();
      window.location.replace("login.html");
      return null;
    }
    return resp;
  }

  return { login, logout, isLoggedIn, getPhone, apiFetch };
})();
