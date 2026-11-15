"use strict";
// Hosted-only request adapter. The local app.js and its numerical UI are reused.
(() => {
  const nativeFetch = window.fetch.bind(window);
  let csrf = null;
  let expired = false;
  let gate = null;
  let resume = null;
  let dialog = null;
  const sessionReady = nativeFetch("/auth/session", {cache: "no-store", credentials: "same-origin"})
    .then(async (response) => {
      if (!response.ok) throw new Error("Session could not be checked.");
      const value = await response.json(); csrf = value.csrf;
      if (!value.authenticated) showExpired();
      return value;
    });
  // Attach a rejection handler even if initial page requests fail before a POST.
  sessionReady.catch(() => showExpired());

  function showExpired() {
    if (expired) return;
    expired = true;
    gate = new Promise((resolve) => { resume = resolve; });
    dialog = document.createElement("dialog"); dialog.setAttribute("aria-labelledby", "cloud-session-title");
    const title = document.createElement("h2"); title.id = "cloud-session-title"; title.textContent = "Sign in to continue";
    const explanation = document.createElement("p"); explanation.textContent = "Your session expired. Your edited inputs remain open.";
    const link = document.createElement("a"); link.href = "/login"; link.target = "_blank"; link.rel = "noopener";
    link.textContent = "Sign in"; link.className = "button primary";
    const continueButton = document.createElement("button"); continueButton.type = "button";
    continueButton.textContent = "Continue"; continueButton.className = "button secondary";
    continueButton.addEventListener("click", async () => {
      if (!await refreshSession()) explanation.textContent = "Complete sign-in in the new tab, then continue here.";
    });
    dialog.append(title, explanation, link, document.createTextNode(" "), continueButton);
    dialog.addEventListener("cancel", (event) => event.preventDefault());
    document.body.append(dialog); dialog.showModal();
  }

  async function refreshSession() {
    try {
      const response = await nativeFetch("/auth/session", {cache: "no-store", credentials: "same-origin"});
      const value = await response.json();
      if (response.ok && value.authenticated) {
        csrf = value.csrf; expired = false;
        if (dialog) { dialog.close(); dialog.remove(); dialog = null; }
        if (resume) resume();
        gate = null; resume = null;
        return true;
      }
    } catch { /* Keep the editor open when connectivity is unavailable. */ }
    return false;
  }

  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === "string" || input instanceof URL ? input : input.url, window.location.href);
    if (url.origin !== window.location.origin) return nativeFetch(input, options);
    const method = (options.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
    const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      await sessionReady.catch(() => null);
    }
    // Pause polling and editing requests after expiry, without reloading the page.
    // The first rejected request is not automatically replayed.
    if (expired && url.pathname !== "/auth/logout") await gate;
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      if (csrf) headers.set("X-CSRF-Token", csrf);
    }
    const response = await nativeFetch(input, {...options, headers, credentials: "same-origin"});
    if (response.status === 401) showExpired();
    return response;
  };

  window.addEventListener("focus", async () => {
    if (expired) await refreshSession();
  });

  document.addEventListener("click", async (event) => {
    const link = event.target.closest?.("a.download-link");
    if (!link) return;
    event.preventDefault();
    if (await refreshSession()) window.location.assign(link.href);
    else showExpired();
  });

  document.getElementById("cloud-logout").addEventListener("click", async () => {
    try {
      const response = await window.fetch("/auth/logout", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      if (response.ok || response.status === 401) window.location.replace("/login");
      else throw new Error("Logout could not be completed.");
    } catch (error) {
      const notice = document.getElementById("notification");
      notice.textContent = error.message; notice.className = "notice warning"; notice.hidden = false;
    }
  });
})();
