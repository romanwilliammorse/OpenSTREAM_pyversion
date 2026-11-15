"use strict";

// Browser-only presentation. Input interpretation and every solver calculation
// remain in the native Python package; no formula is duplicated here.
const $ = (id) => document.getElementById(id);
const state = {
  framework: null, schema: null, baseline: null, inputs: null,
  invalid: new Map(), rows: new Map(), changes: [], selectedRun: null,
  activeRun: null, data: null, dataset: "physical", pollTimer: null,
  loading: false, submitting: false, quantities: new Map(), loadSequence: 0, selectionSequence: 0,
};
// Submissions are immutable; names must come from the selected run, never
// from the current editor or the server's case-normalized change list.
const savedInputs = new Map();
const pendingInputs = new Map();
const frameworkNames = {Mixture: "Mixture", TwoFluid: "Two-fluid", ThreeField: "Three-field", FourField: "Four-field"};
const terminalStates = new Set(["completed", "failed", "cancelled"]);
const primaryFieldPrefixes = ["", "liquid.", "vapor.", "film.", "drop.", "film.base.", "film.wave."];
const copy = (value) => JSON.parse(JSON.stringify(value));
const equal = (left, right) => JSON.stringify(left) === JSON.stringify(right);
const fieldId = (field) => `${field.group}.${field.key}`;
const domId = (value) => value.replace(/[^a-zA-Z0-9_-]/g, "-");
const readable = (value) => value === undefined || value === null ? "—" : typeof value === "string" ? value : JSON.stringify(value);
const numberText = (value) => typeof value === "number" ? (value === 0 ? "0" : Math.abs(value) < 0.001 || Math.abs(value) >= 1e5 ? value.toExponential(5) : Number(value.toPrecision(7)).toString()) : String(value);

function inputCaseName(inputs, fallback = "Unnamed case") {
  const name = inputs?.model?.ID;
  return typeof name === "string" && name.trim() ? name.trim() : fallback;
}

function runCaseName(run, submission) {
  return inputCaseName(submission?.inputs, run.is_reference ? "TUTORIAL1" : "Unnamed case");
}

async function loadSavedInputs(run) {
  if (savedInputs.has(run.id)) return savedInputs.get(run.id);
  if (!pendingInputs.has(run.id)) {
    pendingInputs.set(run.id, api(`/files/${encodeURIComponent(run.id)}/submitted_inputs.json`)
      .then((submission) => { savedInputs.set(run.id, submission); return submission; })
      .finally(() => pendingInputs.delete(run.id)));
  }
  return pendingInputs.get(run.id);
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  $("sidebar").hidden = collapsed;
  $("toggle-sidebar").setAttribute("aria-expanded", String(!collapsed));
  $("toggle-sidebar").setAttribute("aria-label", collapsed ? "Show sidebar" : "Hide sidebar");
  $("toggle-sidebar").title = collapsed ? "Show sidebar" : "Hide sidebar";
  try { localStorage.setItem("openstream-sidebar-collapsed", String(collapsed)); } catch { /* Optional preference. */ }
  if (state.data && !$("results-view").hidden && window.Plotly) requestAnimationFrame(() => Plotly.Plots.resize($("profile-plot")));
}

function primaryQuantityFields(names, suffix) {
  const allowed = new Set(primaryFieldPrefixes.map((prefix) => `${prefix}${suffix}`));
  return names.filter((name) => allowed.has(name));
}

function referenceIndexForTime(referenceTimes, physicalTime) {
  if (!Array.isArray(referenceTimes) || !Number.isFinite(physicalTime)) return -1;
  return referenceTimes.findIndex((time) => Number.isFinite(time) && Math.abs(time - physicalTime) <= 1e-12);
}

function assertInputDocumentVersion(document) {
  if (document && Object.prototype.hasOwnProperty.call(document, "schema") && document.schema !== "openstream-gui-input-v1") {
    throw new Error(`Unsupported input schema ${JSON.stringify(document.schema)}. Expected openstream-gui-input-v1.`);
  }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, {cache: "no-store", ...options,
    headers: {...(options.body ? {"Content-Type": "application/json"} : {}), ...options.headers}});
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : {error: await response.text()};
  if (!response.ok) {
    const error = new Error(data.error || data.message || `Request failed (${response.status}).`);
    error.details = data;
    throw error;
  }
  return data;
}

function notice(message, kind = "info") {
  $("notification").textContent = message;
  $("notification").className = `notice ${kind}`;
  $("notification").hidden = !message;
}

function showView(view) {
  for (const name of ["inputs", "results"]) {
    $(`${name}-view`).hidden = name !== view;
    $(`${name}-tab`).classList.toggle("active", name === view);
    if (name === view) $(`${name}-tab`).setAttribute("aria-current", "page");
    else $(`${name}-tab`).removeAttribute("aria-current");
  }
  if (view === "results" && state.data) requestAnimationFrame(renderPlot);
}

function inputGroup(inputs, group) {
  return group === "bc" || group === "boundary" ? inputs.bc?.[0] : inputs[group];
}

function getInput(field, inputs = state.inputs) { return inputGroup(inputs, field.group)?.[field.key]; }
function putInput(field, value) {
  if (field.group === "bc" || field.group === "boundary") {
    if (!state.inputs.bc) state.inputs.bc = [{}];
    state.inputs.bc[0][field.key] = value;
  } else {
    if (!state.inputs[field.group]) state.inputs[field.group] = {};
    state.inputs[field.group][field.key] = value;
  }
}

function fieldReference(field) { return field.reference !== undefined ? field.reference : getInput(field, state.baseline.inputs); }
function fieldChanged(field) { return state.invalid.has(fieldId(field)) || !equal(getInput(field), fieldReference(field)); }

function parseField(field, control) {
  if (field.kind === "bool") return control.checked;
  const raw = control.value.trim();
  if (["string", "enum"].includes(field.kind)) return raw;
  if (!raw) throw new Error("Enter a value; an empty field is not a numerical value.");
  if (["vector", "matrix"].includes(field.kind)) {
    let value;
    if (raw.startsWith("[")) {
      try { value = JSON.parse(raw); } catch { throw new Error("Use a JSON array, for example [1, 2] or [[1], [2]]. Quote \"NaN\" if required."); }
    } else {
      value = raw.split(/[\s,;]+/).map((token) => token === "NaN" ? "NaN" : Number(token));
    }
    const valid = (x) => Array.isArray(x) ? x.every(valid) : x === "NaN" || (typeof x === "number" && Number.isFinite(x));
    if (!Array.isArray(value) || !value.length || !valid(value)) throw new Error("Use a nonempty numerical array. The supported NaN sentinel is the string \"NaN\".");
    if (field.kind === "matrix" && !value.every(Array.isArray)) throw new Error("Enter matrix rows as nested arrays, for example [[1], [1]].");
    return value;
  }
  if (raw === "NaN") return "NaN";
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error("Enter a finite number using decimal or scientific notation.");
  if (field.kind === "integer" && !Number.isInteger(value)) throw new Error("Enter a whole number.");
  return value;
}

function setControl(control, field, value) {
  if (field.kind === "bool") control.checked = Boolean(value);
  else control.value = Array.isArray(value) ? JSON.stringify(value) : value === null || value === undefined ? "" : String(value);
}

function createField(field) {
  const id = fieldId(field), inputId = `field-${domId(id)}`;
  const row = element("tr", "field-row");
  row.dataset.field = id;
  const nameCell = element("td");
  const nameLine = element("div", "field-name-line");
  const label = element("label", "field-label", field.label || field.key);
  label.htmlFor = inputId;
  nameLine.append(label);
  if (field.unit) nameLine.append(element("span", "field-unit", field.unit));
  const inactiveBadge = element("span", "field-inactive", "Inactive"); inactiveBadge.hidden = true; nameLine.append(inactiveBadge);
  nameCell.append(nameLine);
  if (field.label && field.label !== field.key) nameCell.append(element("span", "field-key", field.key));
  else label.classList.add("parameter-name");
  const details = element("details", "field-details");
  const detailsSummary = element("summary", "", "Details"); detailsSummary.setAttribute("aria-label", `Details for ${field.key}`); details.append(detailsSummary);
  const description = element("p", "field-description", field.description || "");
  description.id = `${inputId}-description`;
  details.append(description);
  const applicability = element("p", `field-applicability${field.active === false ? " inactive" : ""}`, `${field.active === false ? "Inactive in this framework · " : ""}${field.applicability || ""}`);
  applicability.hidden = !field.applicability; details.append(applicability); nameCell.append(details);
  const valueCell = element("td");
  const valueWrapper = element("div", "field-value-control");
  let control;
  if (field.kind === "enum") {
    control = element("select");
    const choices = field.choices || [];
    for (const choice of choices) {
      const normalized = typeof choice === "string" ? {value: choice, supported: true} : choice;
      const option = element("option", "", `${normalized.value}${normalized.supported === false ? " — unsupported" : ""}`);
      option.value = normalized.value;
      option.disabled = normalized.supported === false;
      if (normalized.reason) option.title = normalized.reason;
      control.append(option);
    }
    const value = getInput(field);
    if (!choices.some((choice) => (choice.value ?? choice) === value)) {
      const option = element("option", "", value);
      option.value = value;
      control.append(option);
    }
  } else if (["vector", "matrix"].includes(field.kind)) {
    control = element("textarea"); control.rows = field.kind === "matrix" ? 2 : 1;
    control.spellcheck = false;
  } else {
    control = element("input");
    control.type = field.kind === "bool" ? "checkbox" : "text";
    if (["number", "integer"].includes(field.kind)) control.inputMode = "decimal";
    control.autocomplete = "off";
    control.spellcheck = false;
  }
  control.id = inputId;
  control.name = id;
  control.setAttribute("aria-describedby", `${inputId}-description ${inputId}-error`);
  control.disabled = field.editable === false;
  setControl(control, field, getInput(field));
  if (field.kind === "bool") {
    const boolWrapper = element("label", "boolean-control");
    boolWrapper.htmlFor = inputId;
    const boolText = element("span", "", control.checked ? "Enabled" : "Disabled");
    boolWrapper.append(control, boolText);
    control.addEventListener("change", () => {boolText.textContent = control.checked ? "Enabled" : "Disabled";});
    valueWrapper.append(boolWrapper);
  } else valueWrapper.append(control);
  const reset = element("button", "field-reset", "↺");
  reset.type = "button";
  reset.title = `Reset ${field.key} to reference`;
  reset.setAttribute("aria-label", reset.title);
  reset.addEventListener("click", () => {
    setControl(control, field, fieldReference(field));
    control.dispatchEvent(new Event(field.kind === "bool" || field.kind === "enum" ? "change" : "input", {bubbles: true}));
  });
  valueWrapper.append(reset);
  valueCell.append(valueWrapper);
  if (field.kind === "matrix") details.append(element("p", "field-help", "Rows = axial segments; columns = walls. Use nested JSON arrays."));
  else if (field.kind === "vector") details.append(element("p", "field-help", `Array${field.shape ? ` · shape ${field.shape}` : ""}. JSON or comma-separated values.`));
  if (field.editable === false) details.append(element("p", "field-help", field.readonly_reason || "Fixed for this steady-baseline interface."));
  const error = element("p", "field-error"); error.id = `${inputId}-error`; error.hidden = true; valueCell.append(error);
  const referenceCell = element("td");
  referenceCell.append(element("code", "field-reference", readable(fieldReference(field))));
  const source = field.source || {};
  const sourceText = source.kind === "explicit" ? "Original input file" : "Upstream default";
  const sourceLocation = [source.file, source.line ? `line ${source.line}` : "", source.record !== undefined ? `record ${source.record}` : ""].filter(Boolean).join(" · ");
  const sourceLabel = element("span", "source-label", `Reference: ${sourceText}${sourceLocation ? ` · ${sourceLocation}` : ""}`);
  details.append(sourceLabel);
  if (field.effective_reference !== undefined && !equal(field.effective_reference, fieldReference(field))) referenceCell.append(element("span", "effective-value", `→ ${readable(field.effective_reference)}`));
  const defaultCell = element("td"); defaultCell.append(element("code", "field-default", field.default === null ? "Required" : readable(field.default)));
  if (field.effective_default !== undefined && !equal(field.effective_default, field.default)) defaultCell.append(element("span", "effective-value", `→ ${readable(field.effective_default)}`));
  if (field.default_note) details.append(element("span", "source-label", `Default: ${field.default_note}`));
  row.append(nameCell, valueCell, referenceCell, defaultCell);
  const onEdit = () => {
    try {
      const value = parseField(field, control); putInput(field, value); state.invalid.delete(id);
      error.hidden = true; control.removeAttribute("aria-invalid"); row.classList.remove("has-error");
    } catch (issue) {
      state.invalid.set(id, issue.message); error.textContent = issue.message; error.hidden = false;
      control.setAttribute("aria-invalid", "true"); row.classList.add("has-error");
    }
    $("validation").hidden = true;
    updateChanges();
  };
  control.addEventListener(field.kind === "bool" || field.kind === "enum" ? "change" : "input", onEdit);
  state.rows.set(id, {row, reset, field, control, applicability, inactiveBadge, search: `${field.group} ${field.key} ${field.label} ${field.description} ${field.unit} ${field.applicability}`.toLowerCase()});
  return row;
}

function renderEditor() {
  state.rows.clear(); state.invalid.clear();
  const form = $("input-editor"); form.replaceChildren(); $("group-links").replaceChildren();
  const groups = state.schema.groups || [...new Set(state.schema.fields.map((f) => f.group))].map((key) => ({key, label: key}));
  for (const group of groups) {
    const fields = state.schema.fields.filter((field) => field.group === group.key);
    if (!fields.length) continue;
    const section = element("section", "input-group"); section.id = `group-${domId(group.key)}`;
    const heading = element("div", "input-group-heading");
    const h2 = element("h2", "", group.label); h2.id = `${section.id}-title`; section.setAttribute("aria-labelledby", h2.id);
    heading.append(h2, element("span", "", `${fields.length} inputs`)); section.append(heading);
    const table = element("table", "field-table"); table.setAttribute("aria-label", `${group.label} inputs`);
    const thead = element("thead"), headerRow = element("tr");
    for (const title of ["Parameter / units", "Value", "Reference", "Default"]) { const th = element("th", "", title); th.scope = "col"; if (title === "Reference") th.title = "Selected steady TUTORIAL1 baseline"; if (title === "Default") th.title = "Original input-definition default"; headerRow.append(th); }
    thead.append(headerRow); const tbody = element("tbody");
    for (const field of fields) tbody.append(createField(field));
    table.append(thead, tbody); section.append(table); form.append(section);
    const anchor = element("a", "", group.label); anchor.href = `#${section.id}`;
    anchor.addEventListener("click", () => {$("input-search").value = ""; $("changed-only").checked = false; filterFields();});
    $("group-links").append(anchor);
  }
  $("input-count").textContent = state.schema.fields.length;
  updateChanges();
}

function updateChanges() {
  state.changes = state.schema.fields.filter(fieldChanged);
  for (const entry of state.rows.values()) {
    const changed = fieldChanged(entry.field); entry.row.classList.toggle("is-changed", changed); entry.reset.disabled = !changed || entry.field.editable === false;
    const conditions = entry.field.conditions || [];
    const inactive = entry.field.active === false || conditions.some((condition) => !condition.values.includes(inputGroup(state.inputs, condition.group)?.[condition.key]));
    const reasons = conditions.map((condition) => `${condition.key} = ${condition.values.join(" or ")}`);
    entry.applicability.textContent = [inactive ? "Inactive for current settings" : "", entry.field.applicability, reasons.length ? `Used when ${reasons.join("; ")}` : ""].filter(Boolean).join(" · ");
    entry.applicability.hidden = !entry.applicability.textContent;
    entry.applicability.classList.toggle("inactive", inactive);
    entry.inactiveBadge.hidden = !inactive;
    entry.inactiveBadge.title = entry.applicability.textContent;
  }
  const count = state.changes.length;
  $("case-badge").textContent = count ? "Custom inputs" : "Reference inputs";
  $("case-badge").className = `badge ${count ? "custom" : "reference"}`;
  $("change-summary").textContent = count ? `${count} edited · unverified` : "Reference inputs";
  $("dock-case").textContent = `${inputCaseName(state.inputs)} · ${frameworkNames[state.framework]}`;
  filterFields(); updateRunControls();
}

function filterFields() {
  const query = $("input-search").value.toLowerCase().trim(), changedOnly = $("changed-only").checked;
  let visible = 0;
  for (const entry of state.rows.values()) { entry.row.hidden = (query && !entry.search.includes(query)) || (changedOnly && !fieldChanged(entry.field)); if (!entry.row.hidden) visible++; }
  document.querySelectorAll(".input-group").forEach((section) => { section.hidden = ![...section.querySelectorAll(".field-row")].some((row) => !row.hidden); });
  $("visible-count").textContent = `${visible} of ${state.rows.size} inputs`;
  $("no-fields").hidden = visible !== 0;
}

async function loadFramework(framework, {imported = null, quiet = false, requestSequence = null} = {}) {
  const sequence = requestSequence ?? ++state.loadSequence; state.loading = true; updateRunControls();
  try {
    const [schema, baseline] = await Promise.all([api(`/api/schema?framework=${encodeURIComponent(framework)}`), api(`/api/baseline/${encodeURIComponent(framework)}`)]);
    if (sequence !== state.loadSequence) return false;
    state.framework = framework; state.schema = schema; state.baseline = baseline; state.inputs = copy(imported || baseline.inputs);
    $("framework").value = framework; $("case-title").textContent = frameworkNames[framework];
    $("input-search").value = ""; $("changed-only").checked = false; $("validation").hidden = true;
    state.selectedRun = null; state.data = null;
    $("results-empty").hidden = false; $("run-content").hidden = true;
    renderEditor(); if (!quiet) notice("");
    $("model-picker").hidden = true; $("workspace").hidden = false; showView("inputs");
    if (schema.version) $("app-version").textContent = `Version ${schema.version}`;
    return true;
  } catch (error) { if (sequence === state.loadSequence) { $("framework").value = state.framework || ""; notice(`Could not load the baseline: ${error.message}`, "error"); } return false; }
  finally { if (sequence === state.loadSequence) {state.loading = false; updateRunControls();} }
}

function payload() { return {framework: state.framework, inputs: copy(state.inputs)}; }

function showValidation(valid, messages) {
  const panel = $("validation"); panel.replaceChildren(); panel.className = `validation-panel ${valid ? "success" : "error"}`; panel.hidden = false;
  panel.append(element("h3", "", valid ? "Input checks passed" : "Inputs need attention"));
  const list = element("ul"); for (const message of messages) list.append(element("li", "", message)); panel.append(list);
}

async function validateInputs({forRun = false, submission = payload()} = {}) {
  if (state.invalid.size) { showValidation(false, [...state.invalid].map(([field, message]) => `${field}: ${message}`)); showView("inputs"); $("validation").scrollIntoView({block: "center", behavior: "smooth"}); return false; }
  $("validate-inputs").disabled = true;
  try {
    const result = await api("/api/validate", {method: "POST", body: JSON.stringify(submission)});
    if (result.valid === false) throw new Error(result.error || "Inputs did not pass validation.");
    showValidation(true, [result.is_reference ? "Matches the steady reference." : "Custom inputs accepted. MATLAB equivalence and physical validity remain unverified.", ...(result.warnings || [])]);
    if (!forRun) { showView("inputs"); $("validation").scrollIntoView({block: "center", behavior: "smooth"}); }
    return true;
  } catch (error) {showValidation(false, error.details?.errors || [error.message]); showView("inputs"); $("validation").scrollIntoView({block: "center", behavior: "smooth"}); return false;}
  finally { updateRunControls(); }
}

function updateRunControls() {
  const busy = !!state.activeRun && !terminalStates.has(state.activeRun.status);
  const locked = state.loading || state.submitting;
  $("run-case").disabled = locked || !state.inputs || busy;
  $("validate-inputs").disabled = locked || !state.inputs;
  $("cancel-run").hidden = !busy;
  $("framework").disabled = locked;
  document.querySelectorAll("#model-picker [data-framework]").forEach((button) => {button.disabled = locked;});
  document.querySelectorAll("#history button").forEach((button) => {button.disabled = state.submitting;});
  $("save-inputs").disabled = !state.inputs || locked;
  $("reset-case").disabled = !state.inputs || locked;
  $("load-inputs").disabled = locked;
}

async function startRun() {
  if (state.loading || state.submitting || (state.activeRun && !terminalStates.has(state.activeRun.status))) return;
  const submission = payload();
  state.submitting = true; updateRunControls();
  try {
    if (!await validateInputs({forRun: true, submission})) return;
    const result = await api("/api/runs", {method: "POST", body: JSON.stringify(submission)});
    state.activeRun = result.run || result; state.selectedRun = state.activeRun; state.data = null;
    savedInputs.set(state.activeRun.id, submission);
    renderRun(state.activeRun); showView("results"); notice("");
    await refreshHistory(); schedulePoll();
  } catch (error) { notice(`The run could not start: ${error.message}`, "error"); }
  finally {state.submitting = false; updateRunControls();}
}

async function cancelRun() {
  if (!state.activeRun) return;
  $("cancel-run").disabled = true;
  try {
    const result = await api(`/api/runs/${encodeURIComponent(state.activeRun.id)}/cancel`, {method: "POST", body: "{}"});
    state.activeRun = result.run || result;
    if (state.selectedRun?.id === state.activeRun.id) {state.selectedRun = state.activeRun; renderRun(state.activeRun);}
    notice("Cancellation requested. The run record and any completed output remain available."); schedulePoll();
  } catch (error) {notice(`Could not cancel the run: ${error.message}`, "error");}
  finally {$("cancel-run").disabled = false; updateRunControls();}
}

function schedulePoll() {
  clearTimeout(state.pollTimer);
  if (state.activeRun && !terminalStates.has(state.activeRun.status)) state.pollTimer = setTimeout(pollRun, 1000);
}

async function pollRun() {
  if (!state.activeRun) return;
  try {
    const run = await api(`/api/runs/${encodeURIComponent(state.activeRun.id)}`); state.activeRun = run;
    if (state.selectedRun?.id === run.id) {
      state.selectedRun = run; renderRun(run);
      if (terminalStates.has(run.status)) await loadRunData(run);
    }
    if (terminalStates.has(run.status)) await refreshHistory();
  } catch (error) {notice(`Could not refresh solver progress: ${error.message}. Retrying…`, "warning");}
  finally {updateRunControls(); schedulePoll();}
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"});
}

async function refreshHistory() {
  try {
    const response = await api("/api/runs"); const runs = Array.isArray(response) ? response : response.runs || [];
    // A missing legacy submission must not hide the remaining history.
    await Promise.allSettled(runs.map(loadSavedInputs));
    $("history").replaceChildren();
    if (!runs.length) $("history").append(element("p", "muted small", "No saved runs."));
    for (const run of runs) {
      const button = element("button", `history-item${state.selectedRun?.id === run.id ? " selected" : ""}`); button.type = "button";
      button.append(element("strong", "", `${frameworkNames[run.framework] || run.framework} · ${runCaseName(run, savedInputs.get(run.id))}`));
      const meta = element("span", "history-meta"); meta.append(element("span", "", formatDate(run.created_at)), element("span", "", run.status)); button.append(meta);
      button.title = `Open run ${run.id}`; button.addEventListener("click", () => selectRun(run.id)); $("history").append(button);
      if (!state.activeRun && ["running", "queued"].includes(run.status)) { state.activeRun = run; schedulePoll(); }
    }
    updateRunControls();
  } catch (error) { $("history").replaceChildren(element("p", "muted small", `Run history unavailable: ${error.message}`)); }
}

async function selectRun(id) {
  if (state.submitting) return;
  const selection = ++state.selectionSequence;
  const requestSequence = ++state.loadSequence;
  state.loading = true; updateRunControls();
  try {
    const run = await api(`/api/runs/${encodeURIComponent(id)}`);
    const submission = await loadSavedInputs(run);
    if (selection !== state.selectionSequence) return;
    if (!submission?.inputs || submission.framework !== run.framework) throw new Error("Saved inputs do not identify this run's model.");
    if (!await loadFramework(run.framework, {imported: submission.inputs, quiet: true, requestSequence}) || selection !== state.selectionSequence) return;
    state.selectedRun = run; state.data = null;
    renderRun(run); showView("results");
    if (["running", "queued"].includes(run.status)) {state.activeRun = run; schedulePoll();}
    else await loadRunData(run);
    await refreshHistory();
  } catch (error) { if (selection === state.selectionSequence) notice(`Could not open the run: ${error.message}`, "error"); }
  finally { if (requestSequence === state.loadSequence) {state.loading = false; updateRunControls();} }
}

function setStatusCard(name, title, detail, kind = "") {
  $(`${name}-status`).textContent = title;
  $(`${name}-detail`).textContent = detail;
  $(`${name}-card`).className = `result-status ${kind}`;
}

function progressText(event) {
  if (typeof event === "string") return event;
  const parts = [];
  if (event.phase || event.stage) parts.push(event.phase || event.stage);
  if (event.message) parts.push(event.message);
  for (const key of ["iteration", "step", "time", "residual", "mass_error", "energy_error"]) if (event[key] !== undefined) parts.push(`${key}=${numberText(event[key])}`);
  return parts.length ? parts.join(" · ") : JSON.stringify(event);
}

function renderRun(run) {
  $("results-empty").hidden = true; $("run-content").hidden = false;
  const label = frameworkNames[run.framework] || run.framework || "Simulation";
  $("run-title").textContent = `${label} · ${runCaseName(run, savedInputs.get(run.id))}`;
  $("run-meta").textContent = formatDate(run.created_at);
  $("run-status").textContent = run.status || "queued";
  $("run-status").className = `badge ${run.status === "failed" ? "error" : run.status === "completed" ? "success" : ""}`;
  const busy = !terminalStates.has(run.status);
  $("run-progress").hidden = !busy;
  const events = Array.isArray(run.progress) ? run.progress : run.progress ? [run.progress] : [];
  const latest = events.at(-1) || {};
  $("progress-label").textContent = run.phase || latest.phase || latest.stage || (run.status === "queued" ? "Queued" : "Solving");
  const percent = latest.percent ?? latest.percentage;
  if (typeof percent === "number") {$("progress-bar").value = percent; $("progress-bar").max = 100; $("progress-detail").textContent = `${percent.toFixed(1)}%`;} else {$("progress-bar").removeAttribute("value"); $("progress-detail").textContent = latest.iteration !== undefined ? `Iteration ${latest.iteration}` : "";}
  $("progress-message").textContent = events.length ? progressText(latest) : "Waiting for the first solver event…";
  $("event-log").textContent = events.length ? events.map(progressText).join("\n") : "No solver events recorded.";
  if (run.converged === true) setStatusCard("numerical", "Converged", run.convergence_message || "The solver satisfied its configured convergence criteria.", "good");
  else if (run.converged === false) setStatusCard("numerical", "Not converged", run.convergence_message || "The solver did not satisfy its configured convergence criteria.", "error");
  else setStatusCard("numerical", busy ? "In progress" : "Not established", busy ? "Convergence will be reported by the native solver." : "No completed convergence result is available.");
  const reference = run.reference || {};
  if (reference.status === "passed") setStatusCard("reference", "Archived profiles agree", reference.message || "The original archived MATLAB baseline comparison passed.", "good");
  else if (reference.status === "failed") setStatusCard("reference", "Comparison failed", reference.message || "The run did not meet the baseline comparison tolerances.", "error");
  else setStatusCard("reference", run.is_reference ? "Not yet compared" : "Unverified", reference.message || (run.is_reference ? "A reference result is reported only after the numerical comparison." : "Modified inputs are outside the four verified steady baseline cases."), run.is_reference ? "" : "warning");
  const physical = run.physical || {};
  if (physical.status === "passed") setStatusCard("physical", "Reported checks passed", physical.message || "Available consistency checks passed. This is not experimental validation.", "good");
  else if (physical.status === "failed") setStatusCard("physical", "Consistency checks failed", physical.message || "Inspect the diagnostics. Numerical convergence does not establish physical consistency.", "error");
  else setStatusCard("physical", "Not assessed", physical.message || "No complete physical-consistency assessment is available for this run.");
  $("run-error").hidden = !run.error; $("run-error").textContent = typeof run.error === "object" ? JSON.stringify(run.error, null, 2) : run.error || "";
  $("plots-panel").hidden = !state.data;
  renderDownloads(run.files || []);
  const diagnostics = $("diagnostic-details"); diagnostics.replaceChildren();
  const details = {run_id: run.id, case_name: runCaseName(run, savedInputs.get(run.id)), created_at: run.created_at, framework: run.framework, input_case: run.is_reference ? "Unchanged reference inputs" : "Custom inputs", ...(run.reference ? {reference: run.reference} : {}), ...(physical.diagnostics ? {physical_diagnostics: physical.diagnostics} : {})};
  diagnostics.append(element("pre", "diagnostic-json", JSON.stringify(details, null, 2)));
  updateRunControls();
}

function renderDownloads(files) {
  $("download-links").replaceChildren(); $("primary-downloads").replaceChildren();
  const normalized = Array.isArray(files) ? files : Object.entries(files).map(([name, url]) => ({name, url}));
  for (const file of normalized) {
    const name = typeof file === "string" ? file : file.name;
    const url = typeof file === "string" ? `/files/${encodeURIComponent(state.selectedRun.id)}/${file.split("/").map(encodeURIComponent).join("/")}` : file.url;
    if (!url || !url.startsWith("/")) continue;
    const isArchive = name.toLowerCase().endsWith(".zip");
    const link = element("a", `download-link${isArchive ? " primary-download" : ""}`, isArchive ? "Download ZIP" : name); link.href = url; link.download = name.split("/").at(-1); link.title = name;
    $(isArchive ? "primary-downloads" : "download-links").append(link);
  }
  $("other-downloads").hidden = !$("download-links").children.length;
  $("downloads-panel").hidden = !$("download-links").children.length && !$("primary-downloads").children.length;
}

async function loadRunData(run) {
  if (run.status !== "completed") return;
  try {
    const result = await api(`/api/runs/${encodeURIComponent(run.id)}/data`);
    if (state.selectedRun?.id !== run.id) return;
    state.data = result; const datasets = result.datasets || result;
    $("dataset-select").replaceChildren();
    for (const [key, label] of [["physical", "Physical result"], ["initialization", "Initialization (pseudo-time)"], ["precursor", "Mixture precursor"]]) {
      if (datasets[key] && Object.keys(datasets[key].fields || {}).length) {const option = element("option", "", label); option.value = key; $("dataset-select").append(option);}
    }
    if (!$("dataset-select").options.length) { state.data = null; return; }
    state.dataset = $("dataset-select").value; $("plots-panel").hidden = false; refreshPlotControls();
  } catch (error) {notice(`Numerical plot data could not be loaded: ${error.message}`, "warning");}
}

function selectedDataset() { return (state.data?.datasets || state.data || {})[state.dataset]; }

const quantityDefinitions = [
  ["W", "Mass flow rate"], ["P", "Pressure"], ["H", "Specific enthalpy"], ["U", "Velocity"], ["T", "Temperature"],
  ["X", "Mass fraction / quality"], ["XEQ", "Equilibrium quality"], ["VF", "Phase volume fraction"], ["RHO", "Density"],
  ["HFLUX", "Wall heat flux"], ["LHGR", "Linear heat generation"], ["TWALL", "Wall temperature"],
  ["FREQUENCY", "Wave frequency"], ["ECT", "Slip-induced energy correction"], ["MCT", "Slip-induced momentum correction"],
];

function refreshPlotControls() {
  const dataset = selectedDataset(); if (!dataset) return;
  const oldQuantity = $("quantity-select").value; state.quantities.clear(); $("quantity-select").replaceChildren();
  const fields = dataset.fields || {}, names = Object.keys(fields).filter((name) => Array.isArray(fields[name].values?.[0]) && fields[name].values[0].length === (dataset.z || []).length);
  const grouped = element("optgroup"); grouped.label = "Quantities";
  for (const [suffix, label] of quantityDefinitions) {
    const matches = primaryQuantityFields(names, suffix);
    if (!matches.length) continue;
    const key = `quantity:${suffix}`; state.quantities.set(key, {label, names: matches}); const option = element("option", "", label); option.value = key; grouped.append(option);
  }
  if (grouped.children.length) $("quantity-select").append(grouped);
  const individual = element("optgroup"); individual.label = "Individual output fields";
  for (const name of names.sort()) {const key = `field:${name}`; state.quantities.set(key, {label: name, names: [name]}); const option = element("option", "", name); option.value = key; individual.append(option);}
  $("quantity-select").append(individual);
  if (state.quantities.has(oldQuantity)) $("quantity-select").value = oldQuantity;
  else if (state.quantities.has("quantity:W")) $("quantity-select").value = "quantity:W";
  $("time-select").replaceChildren();
  const times = dataset.time || [];
  times.forEach((time, index) => {const option = element("option", "", `${index === times.length - 1 ? "Final · " : ""}${state.dataset === "initialization" ? "τ" : "t"} = ${numberText(time)} s`); option.value = index; $("time-select").append(option);});
  if (!times.length) {const option = element("option", "", "Final state"); option.value = 0; $("time-select").append(option);}
  $("time-select").value = String(Math.max(0, times.length - 1));
  renderPlot();
}

function traceName(key) {
  const parts = key.split("."); parts.pop();
  return parts.length ? parts.map((part) => ({film: "Film", base: "Base film", wave: "Wave", drop: "Droplets", vapor: "Vapor", liquid: "Liquid", mixture: "Mixture"}[part] || part)).join(" · ") : "Mixture";
}

function makeTraces(field, key, z, timeIndex, color, reference = false) {
  const values = field.values;
  if (!Array.isArray(values) || !values.length) return [];
  const slice = values[timeIndex];
  if (!Array.isArray(slice) || slice.length !== z.length) return [];
  const wallCount = Array.isArray(slice[0]) ? slice[0].length : 1;
  const traces = [];
  for (let wall = 0; wall < wallCount; wall++) {
    const y = slice.map((value) => Array.isArray(value) ? value[wall] : value);
    const component = key.startsWith("film.") || ["HFLUX", "LHGR", "TWALL"].includes(key) ? "wall" : "component";
    traces.push({x: z, y, type: "scatter", mode: "lines", name: `${traceName(key)}${wallCount > 1 ? ` · ${component} ${wall + 1}` : ""}${reference ? " · MATLAB archive" : ""}`, line: {color, width: reference ? 1.6 : 2.2, dash: reference ? "dot" : "solid"}, connectgaps: false,
      hovertemplate: `z = %{x:.5g} m<br>%{y:.7g} ${field.unit || field.units || ""}<extra>%{fullData.name}</extra>`});
  }
  return traces;
}

function renderPlot() {
  if (!state.data || !window.Plotly || $("results-view").hidden) return;
  const dataset = selectedDataset(), quantity = state.quantities.get($("quantity-select").value);
  if (!dataset || !quantity) return;
  const z = dataset.z || [], timeIndex = Number($("time-select").value || 0);
  const colors = ["#2980b9", "#8e44ad", "#d28b26", "#278b61", "#b45455", "#566c83", "#776b9e", "#977342"];
  const physicalTime = dataset.time?.[timeIndex];
  const referenceIndex = referenceIndexForTime(dataset.reference_time, physicalTime);
  const traces = []; let unit = "";
  quantity.names.forEach((key, index) => {
    const field = dataset.fields[key]; unit ||= field.unit || field.units || "";
    traces.push(...makeTraces(field, key, z, timeIndex, colors[index % colors.length]));
    const reference = dataset.reference_fields?.[key];
    if (reference && referenceIndex >= 0) traces.push(...makeTraces(reference, key, dataset.reference_z || z, referenceIndex, colors[index % colors.length], true));
  });
  const annularNote = ["ThreeField", "FourField"].includes(state.selectedRun.framework) && state.dataset !== "precursor" ? "Before annular onset, fields are initialization quantities." : "";
  const referenceNote = dataset.reference_fields ? referenceIndex >= 0 ? "Dotted: MATLAB archive at matching time." : "No archived state at this time; reference omitted." : "";
  $("plot-context").textContent = [state.dataset === "initialization" ? "Pseudo-time, not physical time." : "", annularNote, referenceNote].filter(Boolean).join(" ");
  $("plot-context").hidden = !$("plot-context").textContent;
  const layout = {margin: {l: 75, r: 22, t: 30, b: 85}, paper_bgcolor: "#fcfcfc", plot_bgcolor: "#fcfcfc", font: {family: 'Lato,"Helvetica Neue",Arial,sans-serif', size: 12, color: "#404040"}, hovermode: "closest", xaxis: {title: {text: "Axial position, z (m)", standoff: 12}, gridcolor: "#e1e4e5", zerolinecolor: "#ccc", linecolor: "#ccc", showline: true, mirror: false}, yaxis: {title: {text: `${quantity.label}${unit && unit !== "1" ? ` (${unit})` : ""}`, standoff: 15}, gridcolor: "#e1e4e5", zerolinecolor: "#ccc", exponentformat: "e", automargin: true}, legend: {orientation: "h", y: -0.23, x: 0}, uirevision: `${state.selectedRun.id}:${state.dataset}:${$("quantity-select").value}`, autosize: true};
  Plotly.react($("profile-plot"), traces, layout, {responsive: true, displaylogo: false, modeBarButtonsToRemove: ["select2d", "lasso2d"], toImageButtonOptions: {format: "png", filename: `OpenSTREAM-${state.selectedRun.framework}-${quantity.label.replaceAll(" ", "-")}`, width: 1400, height: 850, scale: 1.5}});
}

function downloadInputs() {
  if (state.invalid.size) {notice("Correct the highlighted input values before saving.", "error"); return;}
  const blob = new Blob([JSON.stringify({schema: "openstream-gui-input-v1", ...payload()}, null, 2) + "\n"], {type: "application/json"});
  const url = URL.createObjectURL(blob), anchor = element("a"); anchor.href = url; anchor.download = `OpenSTREAM-${state.framework}-${state.changes.length ? "custom" : "TUTORIAL1"}.json`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function importInputs(event) {
  const file = event.target.files?.[0]; if (!file) return;
  ++state.selectionSequence;
  try {
    if (file.size > 2 * 1024 * 1024) throw new Error("The input JSON file is larger than 2 MB.");
    const imported = JSON.parse(await file.text());
    assertInputDocumentVersion(imported);
    if (!frameworkNames[imported.framework]) throw new Error("The file must specify Mixture, TwoFluid, ThreeField, or FourField as its framework.");
    if (!imported.inputs || !imported.inputs.model || !imported.inputs.geometry || !imported.inputs.options || !Array.isArray(imported.inputs.bc)) throw new Error("The file must contain model, options, geometry, and bc under inputs. Use Save inputs to create this format.");
    const checked = await api("/api/validate", {method: "POST", body: JSON.stringify({framework: imported.framework, inputs: imported.inputs})});
    if (checked.valid === false) throw new Error(checked.error || "The input file failed validation.");
    if (await loadFramework(imported.framework, {imported: checked.inputs || imported.inputs, quiet: true})) notice(`Loaded ${file.name}. ${checked.is_reference ? "The inputs match the steady reference." : "This is a custom case; equivalence is unverified."}`, "success");
  } catch (error) {notice(`Inputs were not loaded: ${error.message}`, "error");}
  finally {event.target.value = "";}
}

function bindEvents() {
  $("input-editor").addEventListener("submit", (event) => event.preventDefault());
  const chooseFramework = (framework) => { ++state.selectionSequence; return loadFramework(framework); };
  $("framework").addEventListener("change", (event) => chooseFramework(event.target.value));
  document.querySelectorAll("#model-picker [data-framework]").forEach((button) => button.addEventListener("click", async () => {
    if (await chooseFramework(button.dataset.framework)) $("workspace").focus();
  }));
  $("toggle-sidebar").addEventListener("click", () => setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed")));
  $("reset-case").addEventListener("click", () => {state.inputs = copy(state.baseline.inputs); renderEditor(); $("validation").hidden = true; notice("Reference inputs restored.");});
  $("input-search").addEventListener("input", filterFields); $("changed-only").addEventListener("change", filterFields);
  $("inputs-tab").addEventListener("click", () => showView("inputs")); $("results-tab").addEventListener("click", () => showView("results")); $("empty-inputs").addEventListener("click", () => showView("inputs"));
  $("validate-inputs").addEventListener("click", () => validateInputs()); $("run-case").addEventListener("click", startRun); $("cancel-run").addEventListener("click", cancelRun);
  $("refresh-history").addEventListener("click", refreshHistory); $("save-inputs").addEventListener("click", downloadInputs);
  $("load-inputs").addEventListener("click", () => $("input-file").click()); $("input-file").addEventListener("change", importInputs);
  $("dataset-select").addEventListener("change", () => {state.dataset = $("dataset-select").value; refreshPlotControls();});
  $("quantity-select").addEventListener("change", renderPlot); $("time-select").addEventListener("change", renderPlot);
  $("download-chart").addEventListener("click", () => {if (window.Plotly && state.data) Plotly.downloadImage($("profile-plot"), {format: "png", filename: `OpenSTREAM-${state.selectedRun.framework}-profile`, width: 1400, height: 850, scale: 1.5});});
  window.addEventListener("resize", () => {if (state.data && !$("results-view").hidden && window.Plotly) Plotly.Plots.resize($("profile-plot"));});
}

// These pure adapters are exported only to the dependency-free Node checks.
if (typeof module !== "undefined" && module.exports) module.exports = {inputCaseName, runCaseName, primaryQuantityFields, referenceIndexForTime, assertInputDocumentVersion, makeTraces};
if (typeof document !== "undefined") {
  bindEvents();
  let collapsed = false;
  try { collapsed = localStorage.getItem("openstream-sidebar-collapsed") === "true"; } catch { /* Storage may be disabled. */ }
  setSidebarCollapsed(collapsed); updateRunControls();
  Promise.allSettled([refreshHistory(), api("/api/health").then((health) => {$("app-version").textContent = `Version ${health.version}`; $("app-version").title = `Saved runs: ${health.output_root}`;})]);
}
