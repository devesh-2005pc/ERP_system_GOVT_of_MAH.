/* Thin fetch wrapper: attaches JWT, retries once via refresh token on 401,
   and centralizes error surfacing. No secrets are hardcoded here — tokens
   live only in memory + sessionStorage for this tab's session. */
const API_BASE_URL = "http://localhost:8000";
const WS_BASE_URL = "ws://localhost:8000";

const API = (() => {
  let accessToken = sessionStorage.getItem("access_token") || null;
  let refreshToken = sessionStorage.getItem("refresh_token") || null;

  function setTokens(at, rt) {
    accessToken = at;
    refreshToken = rt;
    if (at) sessionStorage.setItem("access_token", at); else sessionStorage.removeItem("access_token");
    if (rt) sessionStorage.setItem("refresh_token", rt); else sessionStorage.removeItem("refresh_token");
  }

  function getAccessToken() { return accessToken; }
  function isAuthenticated() { return !!accessToken; }

  async function rawRequest(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    if (opts.body && !(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
    if (accessToken) headers["Authorization"] = "Bearer " + accessToken;
    const url = path.startsWith("http") ? path : API_BASE_URL + path;
    const res = await fetch(url, Object.assign({}, opts, { headers }));
    return res;
  }

  async function request(path, opts = {}) {
    let res = await rawRequest(path, opts);
    if (res.status === 401 && refreshToken && !opts._retried) {
      const ok = await tryRefresh();
      if (ok) return request(path, Object.assign({}, opts, { _retried: true }));
    }
    if (!res.ok) {
      let detail = "Request failed";
      try { const j = await res.json(); detail = j.error || detail; } catch (e) {}
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.blob();
  }

  async function tryRefresh() {
    try {
      const res = await fetch(API_BASE_URL + "/api/auth/refresh", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) { setTokens(null, null); return false; }
      const data = await res.json();
      setTokens(data.access_token, data.refresh_token);
      return true;
    } catch (e) { return false; }
  }

  async function login(employee_id, password) {
    const res = await fetch(API_BASE_URL + "/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employee_id, password }),
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.error || "Login failed");
    }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return data;
  }

  async function logout() {
    if (refreshToken) {
      try { await fetch(API_BASE_URL + "/api/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refreshToken }) }); } catch (e) {}
    }
    setTokens(null, null);
  }

  const get = (path) => request(path, { method: "GET" });
  const post = (path, body) => request(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined });
  const put = (path, body) => request(path, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined });
  const del = (path) => request(path, { method: "DELETE" });

  function connectWebSocket(onEvent) {
    if (!accessToken) return null;
    const ws = new WebSocket(`${WS_BASE_URL}/ws?token=${encodeURIComponent(accessToken)}`);
    ws.onmessage = (evt) => {
      try { onEvent(JSON.parse(evt.data)); } catch (e) {}
    };
    return ws;
  }

  return { login, logout, isAuthenticated, getAccessToken, get, post, put, del, connectWebSocket };
})();
