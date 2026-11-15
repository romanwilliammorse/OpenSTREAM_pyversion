"use strict";
(() => {
  const form = document.getElementById("login-form");
  const password = document.getElementById("password");
  const error = document.getElementById("login-error");
  const button = form.querySelector("button");
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); button.disabled = true; error.hidden = true;
    try {
      const sessionResponse = await fetch("/auth/session", {cache: "no-store", credentials: "same-origin"});
      if (!sessionResponse.ok) throw new Error("Sign-in is temporarily unavailable.");
      const session = await sessionResponse.json();
      const response = await fetch("/auth/login", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf},
        body: JSON.stringify({password: password.value}),
      });
      password.value = "";
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Sign-in failed.");
      window.location.replace("/");
    } catch (failure) {
      password.value = "";
      error.textContent = failure.message || "Sign-in failed."; error.hidden = false; password.focus();
    } finally { button.disabled = false; }
  });
})();
