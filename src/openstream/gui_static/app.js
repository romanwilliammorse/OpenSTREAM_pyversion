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
// Presentation preferences are isolated by saved run; numerical data stay immutable.
const plotWorkspaces = new Map();
const plotColors = ["#2980b9", "#8e44ad", "#d28b26", "#278b61", "#b45455", "#566c83", "#776b9e", "#977342"];
const plotFont = '"Times New Roman", Times, serif';
const lineDashChoices = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"];
const markerSymbolChoices = ["circle", "circle-open", "square", "square-open", "diamond", "diamond-open", "cross", "x", "triangle-up", "triangle-down", "star"];
const datasetLabels = {physical: "Physical result", initialization: "Initialization (pseudo-time)", precursor: "Mixture precursor", precursor_initialization: "Mixture precursor initialization (pseudo-time)"};
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

function physicalDisplay(run) {
  const physical = run.physical || {};
  if (!["ThreeField", "FourField"].includes(run.framework)) return physical;
  const d = physical.diagnostics || {};
  const historicalAreaOnly = d.phase_volume_closure_role === undefined &&
    physical.status === "failed" && d.physical_consistency === false &&
    d.area_closure_relative_tolerance === 1e-6 && Array.isArray(d.inventory_by_time);
  if (historicalAreaOnly || (d.phase_volume_closure_role === "informational" && physical.status !== "failed")) {
    return {...physical, status: "informational", historicalAreaOnly,
      message: "Phase-volume closure is an informational diagnostic for this model, not a convergence or acceptance criterion." +
        (historicalAreaOnly ? " The original recorded assessment is preserved in Run details and the saved files." : "")};
  }
  return physical;
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
  if (state.data && !$("results-view").hidden && window.Plotly) requestAnimationFrame(resizePlots);
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
  if (view === "results" && state.data) requestAnimationFrame(() => {renderPlot(); renderCustomPlots();});
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
  const physical = physicalDisplay(run);
  if (physical.status === "passed") setStatusCard("physical", "Reported checks passed", physical.message || "Available consistency checks passed. This is not experimental validation.", "good");
  else if (physical.status === "failed") setStatusCard("physical", "Consistency checks failed", physical.message || "Inspect the diagnostics. Numerical convergence does not establish physical consistency.", "error");
  else if (physical.status === "informational") setStatusCard("physical", "Informational diagnostics", physical.message);
  else setStatusCard("physical", "Not assessed", physical.message || "No complete physical-consistency assessment is available for this run.");
  $("run-error").hidden = !run.error; $("run-error").textContent = typeof run.error === "object" ? JSON.stringify(run.error, null, 2) : run.error || "";
  $("plots-panel").hidden = !state.data;
  renderDownloads(run.files || []);
  const diagnostics = $("diagnostic-details"); diagnostics.replaceChildren();
  const details = {run_id: run.id, case_name: runCaseName(run, savedInputs.get(run.id)), created_at: run.created_at, framework: run.framework, input_case: run.is_reference ? "Unchanged reference inputs" : "Custom inputs", ...(run.reference ? {reference: run.reference} : {}), ...(physical.diagnostics ? {physical_diagnostics: physical.diagnostics} : {})};
  if (physical.historicalAreaOnly) details.recorded_physical_assessment = run.physical;
  diagnostics.append(element("pre", "diagnostic-json", JSON.stringify(details, null, 2)));
  updateRunControls();
}

function renderDownloads(files) {
  $("download-links").replaceChildren(); $("primary-downloads").replaceChildren();
  if (state.selectedRun?.status === "completed") {
    for (const [kind, label] of [["inputs", "Inputs CSV"], ["boundary-conditions", "Boundary conditions CSV"], ["geometry", "Geometry CSV"], ["results", "Results CSV"]]) {
      const link = element("a", "download-link csv-download", label);
      link.href = `/api/runs/${encodeURIComponent(state.selectedRun.id)}/export/${kind}.csv`;
      link.download = `${kind}.csv`;
      $("primary-downloads").append(link);
    }
  }
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
    for (const key of Object.keys(datasets)) {
      const label = datasetLabels[key] || key;
      if (datasets[key] && Object.keys(datasets[key].fields || {}).length) {const option = element("option", "", label); option.value = key; $("dataset-select").append(option);}
    }
    if (!$("dataset-select").options.length) { state.data = null; return; }
    state.dataset = $("dataset-select").value; $("plots-panel").hidden = false;
    if (!plotWorkspaces.has(run.id)) plotWorkspaces.set(run.id, {plots: [], nextId: 2, primaryLegend: true});
    refreshPlotControls(); renderPlotBuilderCards();
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
  times.forEach((time, index) => {const option = element("option", "", `${index === times.length - 1 ? "Final · " : ""}${pseudoTime(state.dataset, dataset) ? "τ" : "t"} = ${numberText(time)} s`); option.value = index; $("time-select").append(option);});
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
  const colors = plotColors;
  const physicalTime = dataset.time?.[timeIndex];
  const referenceIndex = referenceIndexForTime(dataset.reference_time, physicalTime);
  const traces = []; let unit = "";
  quantity.names.forEach((key, index) => {
    const field = dataset.fields[key]; unit ||= field.unit || field.units || "";
    traces.push(...makeTraces(field, key, z, timeIndex, colors[index % colors.length]));
    const reference = dataset.reference_fields?.[key];
    if (reference && referenceIndex >= 0) traces.push(...makeTraces(reference, key, dataset.reference_z || z, referenceIndex, colors[index % colors.length], true));
  });
  const annularNote = ["ThreeField", "FourField"].includes(state.selectedRun.framework) && !state.dataset.startsWith("precursor") ? "Before annular onset, fields are initialization quantities." : "";
  const referenceNote = dataset.reference_fields ? referenceIndex >= 0 ? "MATLAB archive at matching time." : "No archived state at this time; reference omitted." : "";
  $("plot-context").textContent = [pseudoTime(state.dataset, dataset) ? "Pseudo-time, not physical time." : "", annularNote, referenceNote].filter(Boolean).join(" ");
  $("plot-context").hidden = !$("plot-context").textContent;
  const legend = plotWorkspace()?.primaryLegend ?? true;
  $("profile-legend").textContent = legend ? "Remove legend" : "Add legend";
  $("profile-legend").setAttribute("aria-pressed", String(legend));
  const workspace = plotWorkspace();
  if (!workspace) return;
  workspace.primaryFigures ||= {};
  const key = `${state.dataset}:${$("quantity-select").value}`;
  const appearance = workspace.primaryFigures[key] ||= {format: defaultPlotFormat(), styles: {}};
  renderPrimaryAppearance(appearance, traces, `${state.selectedRun.id}:${key}`);
  try {
    const layout = plotLayout("Axial position, z (m)", `${quantity.label}${unit && unit !== "1" ? ` (${unit})` : ""}`, legend,
      `${state.selectedRun.id}:${key}`, appearance.format);
    const styled = traces.map((trace, index) => applyTraceStyle(trace, appearance.styles[trace.name] || {}, index));
    $("profile-plot-error").hidden = true; $("profile-plot").hidden = false; $("download-chart").disabled = false;
    Plotly.react($("profile-plot"), styled, layout, plotConfig(`OpenSTREAM-${state.selectedRun.framework}-${quantity.label.replaceAll(" ", "-")}`));
  } catch (error) {
    $("profile-plot-error").textContent = error.message; $("profile-plot-error").hidden = false;
    $("profile-plot").hidden = true; $("download-chart").disabled = true;
    if ($("profile-plot").data) Plotly.purge($("profile-plot"));
  }
}

function insideLegend() {
  return {orientation: "v", x: 0.02, y: 0.98, xref: "paper", yref: "paper",
    xanchor: "left", yanchor: "top", bgcolor: "rgba(252,252,252,0.88)",
    bordercolor: "#d9dfe2", borderwidth: 1, font: {family: plotFont, size: 12}};
}

function escapePlotText(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}
function defaultAxisFormat() {
  return {label: "", min: "", max: "", ticks: "auto", start: "", step: "", positions: "", labels: ""};
}
function defaultPlotFormat() { return {x: defaultAxisFormat(), y: defaultAxisFormat(), revision: 0}; }
function optionalPlotNumber(value, label) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(text) || !Number.isFinite(Number(text))) {
    throw new Error(`${label} must be a finite number.`);
  }
  return Number(text);
}
function axisLayoutSettings(settings = {}, autoTitle = "", axisName = "X") {
  const selected = {...defaultAxisFormat(), ...settings};
  const result = {title: {text: escapePlotText(selected.label.trim() || autoTitle)}, autorange: true,
    tickmode: "auto", tick0: null, dtick: null, tickvals: null, ticktext: null, ticks: "outside", tickfont: {family: plotFont}};
  const min = optionalPlotNumber(selected.min, `${axisName} minimum`), max = optionalPlotNumber(selected.max, `${axisName} maximum`);
  if ((min === null) !== (max === null)) throw new Error(`Enter both ${axisName} limits, or leave both blank for automatic limits.`);
  if (min !== null) {
    if (!(min < max)) throw new Error(`${axisName} minimum must be less than maximum.`);
    if (!Number.isFinite(max - min)) throw new Error(`${axisName} limit span must be finite.`);
    result.range = [min, max]; result.autorange = false;
  }
  if (selected.ticks === "spacing") {
    const step = optionalPlotNumber(selected.step, `${axisName} tick spacing`);
    if (step === null || step <= 0) throw new Error(`${axisName} tick spacing must be greater than zero.`);
    const start = optionalPlotNumber(selected.start, `${axisName} first tick`);
    result.tickmode = "linear"; result.dtick = step; result.tick0 = start ?? 0;
  } else if (selected.ticks === "positions") {
    const entries = selected.positions.split(",").map((value) => value.trim());
    if (!entries.length || entries.length > 2000 || entries.some((value) => !value)) throw new Error(`${axisName} tick positions need 1–2000 comma-separated numbers.`);
    const positions = entries.map((value) => optionalPlotNumber(value, `${axisName} tick position`));
    if (positions.some((value, index) => index > 0 && value <= positions[index - 1])) throw new Error(`${axisName} tick positions must be strictly increasing.`);
    result.tickmode = "array"; result.tickvals = positions;
    if (selected.labels.trim()) {
      const labels = selected.labels.split(",").map((value) => value.trim());
      if (labels.length !== positions.length) throw new Error(`${axisName} tick labels must match the number of tick positions.`);
      result.ticktext = labels.map(escapePlotText);
    }
  } else if (selected.ticks !== "auto") throw new Error(`${axisName} tick mode is unavailable.`);
  return result;
}
function seriesStyle(style = {}, index = 0, fallback = {}) {
  const mode = style.mode ?? fallback.mode ?? "lines";
  const dash = style.dash ?? fallback.line?.dash ?? "solid";
  const symbol = style.symbol ?? fallback.marker?.symbol ?? "circle";
  if (!["lines", "markers", "lines+markers"].includes(mode)) throw new Error("Select lines, points, or lines + points.");
  if (!lineDashChoices.includes(dash)) throw new Error("Select an available line type.");
  if (!markerSymbolChoices.includes(symbol)) throw new Error("Select an available point type.");
  const color = style.color ?? fallback.line?.color ?? fallback.marker?.color ?? plotColors[index % plotColors.length];
  if (!/^#[\da-f]{6}$/i.test(color)) throw new Error("Color must be a six-digit hex value, such as #2980b9.");
  const width = optionalPlotNumber(style.width ?? fallback.line?.width ?? 2.2, "Line width");
  const size = optionalPlotNumber(style.size ?? fallback.marker?.size ?? 6, "Point size");
  if (width === null || width <= 0 || width > 20) throw new Error("Line width must be greater than zero and at most 20 px.");
  if (size === null || size <= 0 || size > 60) throw new Error("Point size must be greater than zero and at most 60 px.");
  return {mode, line: {color, width, dash}, marker: {color, size, symbol}};
}
function applyTraceStyle(trace, style = {}, index = 0) {
  const appearance = seriesStyle(style, index, trace);
  return {...trace, ...appearance, line: {...trace.line, ...appearance.line}, marker: {...trace.marker, ...appearance.marker}};
}

function datasetsOf(data) { return data?.datasets || data || {}; }
function datasetName(key) { return datasetLabels[key] || key; }
function pseudoTime(key, dataset) { return key.includes("initialization") || /pseudo/i.test(dataset.time_label || ""); }

function rectangularShape(value) {
  if (!Array.isArray(value)) {
    if (value === null || (typeof value === "number" && Number.isFinite(value))) return [];
    throw new Error("The selected field contains a nonnumeric value.");
  }
  if (!value.length) throw new Error("The selected field has an empty dimension.");
  const inner = rectangularShape(value[0]);
  for (let index = 1; index < value.length; index++) {
    const shape = rectangularShape(value[index]);
    if (!equal(inner, shape)) throw new Error("The selected field has inconsistent array dimensions.");
  }
  return [value.length, ...inner];
}

function componentIndices(shape) {
  return shape.reduce((indices, size) => indices.flatMap((prefix) =>
    Array.from({length: size}, (_, index) => [...prefix, index])), [[]]);
}

function vectorOptions(data, datasetKey) {
  const dataset = datasetsOf(data)[datasetKey];
  if (!dataset) return [];
  return ["Z", "TIME", ...Object.keys(dataset.fields || {}).sort()];
}

function defaultAxis(data, {dataset = "physical", field = "Z", direction = "channel"} = {}) {
  const datasets = datasetsOf(data);
  if (!datasets[dataset]) dataset = Object.keys(datasets).find((key) => datasets[key]?.fields) || "";
  const keys = vectorOptions(data, dataset);
  if (!keys.includes(field)) field = keys.includes("U") ? "U" : keys.find((key) => !["Z", "TIME"].includes(key)) || "Z";
  return normalizeAxis(data, {dataset, field, direction,
    fixed: Math.max(0, ((direction === "time" ? datasets[dataset]?.z : datasets[dataset]?.time)?.length || 1) - 1), component: []});
}

function normalizeAxis(data, selection) {
  const result = {...selection, component: [...(selection.component || [])]};
  const dataset = datasetsOf(data)[result.dataset];
  if (!dataset) return result;
  if (!vectorOptions(data, result.dataset).includes(result.field)) result.field = "Z";
  if (result.field === "Z") result.direction = "channel";
  if (result.field === "TIME") result.direction = "time";
  const length = result.direction === "time" ? dataset.z?.length : dataset.time?.length;
  if (!Number.isInteger(result.fixed) || result.fixed < 0 || result.fixed >= length) result.fixed = Math.max(0, (length || 1) - 1);
  if (["Z", "TIME"].includes(result.field)) result.component = [];
  else {
    try {
      const trailing = rectangularShape(dataset.fields[result.field].values).slice(2);
      if (result.component.length !== trailing.length || result.component.some((value, index) => !Number.isInteger(value) || value < 0 || value >= trailing[index])) {
        result.component = trailing.map(() => 0);
      }
    } catch { /* The selected field's precise error is displayed in the figure. */ }
  }
  return result;
}

function outputVector(data, selection) {
  const dataset = datasetsOf(data)[selection.dataset];
  if (!dataset) throw new Error("Select an available dataset.");
  const coordinate = selection.field === "Z" || selection.field === "TIME";
  const direction = coordinate ? selection.field === "Z" ? "channel" : "time" : selection.direction;
  if (!["channel", "time"].includes(direction)) throw new Error("Select a vector direction.");
  const axis = direction === "channel" ? dataset.z : dataset.time;
  if (!Array.isArray(axis) || !axis.length || !axis.every(Number.isFinite)) throw new Error("The selected vector has no finite coordinate axis.");
  let values, unit, fixedValue = null;
  const component = selection.component || [];
  if (coordinate) {
    values = [...axis];
    unit = selection.field === "Z" ? "m" : "s";
  } else {
    const field = dataset.fields?.[selection.field];
    if (!field) throw new Error("Select an available result quantity.");
    const shape = rectangularShape(field.values);
    if (shape.length < 2 || shape[0] !== dataset.time?.length || shape[1] !== dataset.z?.length) {
      throw new Error("Field dimensions do not match the saved time and channel coordinates.");
    }
    if (component.length !== shape.length - 2 || component.some((value, index) => !Number.isInteger(value) || value < 0 || value >= shape[index + 2])) {
      throw new Error("Select one valid component of the result array.");
    }
    const fixedSize = direction === "channel" ? shape[0] : shape[1];
    if (!Number.isInteger(selection.fixed) || selection.fixed < 0 || selection.fixed >= fixedSize) throw new Error("The selected state or node is unavailable.");
    const componentValue = (value) => component.reduce((current, index) => current[index], value);
    values = direction === "channel" ? field.values[selection.fixed].map(componentValue)
      : field.values.map((row) => componentValue(row[selection.fixed]));
    unit = field.unit ?? field.units ?? "";
    fixedValue = direction === "channel" ? dataset.time[selection.fixed] : dataset.z[selection.fixed];
  }
  const componentLabel = component.length ? ` [${component.map((index) => index + 1).join(",")}]` : "";
  const label = selection.field === "Z" ? "Axial position, z" : selection.field === "TIME"
    ? pseudoTime(selection.dataset, dataset) ? "Initialization pseudo-time" : "Time" : selection.field + componentLabel;
  return {values, coordinates: [...axis], direction, unit, label, key: selection.field, dataset: selection.dataset,
    fixedValue, pseudo: pseudoTime(selection.dataset, dataset), coordinate};
}

function pairOutputVectors(data, xSelection, ySelection) {
  const x = outputVector(data, xSelection), y = outputVector(data, ySelection);
  if (x.values.length !== y.values.length) throw new Error(`X has ${x.values.length} values; Y has ${y.values.length}. Select vectors with equal lengths.`);
  if (!x.values.some((value, index) => Number.isFinite(value) && Number.isFinite(y.values[index]))) {
    throw new Error("The selected vectors have no finite X/Y pairs. Saved gaps are preserved.");
  }
  const notes = [];
  if (x.direction !== y.direction || !equal(x.coordinates, y.coordinates)) notes.push("Paired by index: X and Y have different coordinates.");
  if (!x.coordinate && !y.coordinate && (x.fixedValue !== y.fixedValue || x.direction !== y.direction || x.pseudo !== y.pseudo)) {
    notes.push("X and Y use different fixed states or nodes.");
  }
  if (x.pseudo || y.pseudo) notes.push("Initialization uses pseudo-time.");
  if (x.values.some((value, index) => value === null || y.values[index] === null)) notes.push("Nonfinite saved values appear as gaps.");
  return {x, y, notes};
}

function buildCustomFigure(data, plot) {
  if (!plot.series.length) throw new Error("Add at least one series.");
  const pairs = plot.series.map((series) => pairOutputVectors(data, series.x, series.y));
  const first = pairs[0];
  if (pairs.some((pair) => pair.x.unit !== first.x.unit || pair.y.unit !== first.y.unit)) {
    throw new Error("Series on one plot must have the same recorded X units and Y units. Use another plot for different units.");
  }
  const traces = pairs.map((pair, index) => applyTraceStyle({
    x: pair.x.values, y: pair.y.values, type: "scatter", mode: plot.mode || "lines",
    name: escapePlotText(plot.series[index].name.trim() || `${pair.y.label} · ${datasetName(pair.y.dataset)}`),
    line: {color: plotColors[index % plotColors.length], width: 2.2},
    marker: {color: plotColors[index % plotColors.length], size: 6}, connectgaps: false,
    hovertemplate: `X = %{x:.7g} ${pair.x.unit}<br>Y = %{y:.7g} ${pair.y.unit}<extra>%{fullData.name}</extra>`,
  }, plot.series[index].style, index));
  const label = (axis) => {
    const names = [...new Set(pairs.map((pair) => pair[axis].label))];
    const unit = first[axis].unit;
    return `${names.length === 1 ? names[0] : axis.toUpperCase()}${unit && unit !== "1" ? ` (${unit})` : unit === "" ? " (unit unavailable)" : " (1)"}`;
  };
  return {traces, xTitle: label("x"), yTitle: label("y"), notes: [...new Set(pairs.flatMap((pair) => pair.notes))]};
}

function plotWorkspace() { return plotWorkspaces.get(state.selectedRun?.id); }
function resizePlots() {
  if (!window.Plotly) return;
  for (const node of document.querySelectorAll("#profile-plot, .custom-plot-canvas")) {
    if (node.data) Plotly.Plots.resize(node);
  }
}
function plotLayout(xTitle, yTitle, legend, revision, format = defaultPlotFormat()) {
  const axis = {gridcolor: "#e1e4e5", zerolinecolor: "#ccc", linecolor: "#ccc", showline: true, exponentformat: "e", automargin: true};
  const x = axisLayoutSettings(format.x, xTitle, "X"), y = axisLayoutSettings(format.y, yTitle, "Y");
  return {margin: {l: 75, r: 22, t: 25, b: 70}, paper_bgcolor: "#fcfcfc", plot_bgcolor: "#fcfcfc",
    font: {family: plotFont, size: 14, color: "#404040"}, hovermode: "closest", hoverlabel: {font: {family: plotFont}},
    xaxis: {...axis, ...x, title: {...x.title, standoff: 12, font: {family: plotFont}}},
    yaxis: {...axis, ...y, title: {...y.title, standoff: 15, font: {family: plotFont}}},
    showlegend: Boolean(legend), legend: insideLegend(), uirevision: `${revision}:${JSON.stringify(format)}`, autosize: true};
}
function plotConfig(filename) {
  return {responsive: true, displaylogo: false, showSendToCloud: false,
    modeBarButtonsToRemove: ["select2d", "lasso2d", "sendDataToCloud"],
    toImageButtonOptions: {format: "png", filename, width: 1400, height: 850, scale: 1.5}};
}
function savePlotImage(node, suffix) {
  if (window.Plotly && node?.data?.length) Plotly.downloadImage(node, {format: "png",
    filename: `OpenSTREAM-${state.selectedRun.framework}-${suffix}`, width: 1400, height: 850, scale: 1.5});
}
function renderCustomPlot(plot) {
  if (!plot.nodes || !state.data || !window.Plotly || $("results-view").hidden) return;
  try {
    const figure = buildCustomFigure(state.data, plot);
    plot.nodes.error.hidden = true; plot.nodes.canvas.hidden = false;
    plot.nodes.context.textContent = figure.notes.join(" "); plot.nodes.context.hidden = !figure.notes.length;
    plot.nodes.save.disabled = false;
    Plotly.react(plot.nodes.canvas, figure.traces, plotLayout(figure.xTitle, figure.yTitle, plot.legend,
      `${state.selectedRun.id}:${plot.id}:${JSON.stringify(plot.series.map((series) => [series.x, series.y]))}`, plot.format),
      plotConfig(`OpenSTREAM-${state.selectedRun.framework}-plot-${plot.id}`));
  } catch (error) {
    plot.nodes.error.textContent = error.message; plot.nodes.error.hidden = false;
    plot.nodes.context.hidden = true; plot.nodes.save.disabled = true; plot.nodes.canvas.hidden = true;
    if (plot.nodes.canvas.data) Plotly.purge(plot.nodes.canvas);
  }
}
function renderCustomPlots() { for (const plot of plotWorkspace()?.plots || []) renderCustomPlot(plot); }

function labelledSelect(container, id, label, choices, value, onChange) {
  const wrapper = element("label", "", label); wrapper.htmlFor = id;
  const control = element("select"); control.id = id;
  for (const choice of choices) { const option = element("option", "", choice.label); option.value = choice.value; control.append(option); }
  control.value = String(value); control.addEventListener("change", onChange);
  wrapper.append(control); container.append(wrapper); return control;
}

function labelledPlotInput(container, id, label, value, placeholder, onChange, {numeric = false, maxLength = 250} = {}) {
  const wrapper = element("label", "", label); wrapper.htmlFor = id;
  const control = element("input"); control.id = id; control.type = "text"; control.value = value ?? "";
  control.placeholder = placeholder; control.maxLength = maxLength;
  if (numeric) control.inputMode = "decimal";
  control.addEventListener("change", onChange); wrapper.append(control); container.append(wrapper);
  return control;
}
function renderPlotFormat(container, format, prefix, onChange) {
  container.replaceChildren();
  const settings = element("details", "plot-format-editor");
  settings.append(element("summary", "", "Plot settings"));
  const grid = element("div", "plot-format-grid"); settings.append(grid);
  for (const axisName of ["x", "y"]) {
    format[axisName] ||= defaultAxisFormat();
    const axis = format[axisName], id = `${prefix}-${axisName}`;
    const panel = element("fieldset", "axis-format-panel"); panel.append(element("legend", "", `${axisName.toUpperCase()} axis`));
    const label = labelledPlotInput(panel, id + "-label", "Axis label", axis.label, "Automatic", (event) => {axis.label = event.target.value; onChange();});
    label.title = "Display label only; saved quantities and units are unchanged.";
    const limits = element("div", "axis-format-row"); panel.append(limits);
    for (const [key, text] of [["min", "Minimum"], ["max", "Maximum"]]) {
      labelledPlotInput(limits, id + "-" + key, text, axis[key], "Automatic", (event) => {axis[key] = event.target.value; onChange();}, {numeric: true});
    }
    const spacing = element("div", "axis-format-row"), positions = element("div", "axis-format-positions");
    labelledSelect(panel, id + "-ticks", "Ticks", [{value: "auto", label: "Automatic"}, {value: "spacing", label: "Spacing"}, {value: "positions", label: "Custom positions"}], axis.ticks,
      (event) => {axis.ticks = event.target.value; spacing.hidden = axis.ticks !== "spacing"; positions.hidden = axis.ticks !== "positions"; onChange();});
    labelledPlotInput(spacing, id + "-start", "First tick", axis.start, "0", (event) => {axis.start = event.target.value; onChange();}, {numeric: true});
    labelledPlotInput(spacing, id + "-step", "Spacing", axis.step, "e.g. 0.1", (event) => {axis.step = event.target.value; onChange();}, {numeric: true});
    labelledPlotInput(positions, id + "-positions", "Positions (comma-separated)", axis.positions, "0, 0.2, 0.4", (event) => {axis.positions = event.target.value; onChange();}, {maxLength: 24000});
    labelledPlotInput(positions, id + "-labels", "Labels (optional, comma-separated)", axis.labels, "Automatic", (event) => {axis.labels = event.target.value; onChange();}, {maxLength: 24000});
    spacing.hidden = axis.ticks !== "spacing"; positions.hidden = axis.ticks !== "positions";
    panel.append(spacing, positions); grid.append(panel);
  }
  const reset = element("button", "text-button", "Reset axes"); reset.type = "button";
  reset.addEventListener("click", () => {
    const nextRevision = (format.revision || 0) + 1;
    Object.assign(format, defaultPlotFormat(), {revision: nextRevision});
    renderPlotFormat(container, format, prefix, onChange);
    container.querySelector("details").open = true; onChange();
  });
  settings.append(reset); container.append(settings);
}
function renderStyleControls(container, style, prefix, index, onChange, fallback = {}) {
  container.replaceChildren();
  // Invalid pending text remains visible in the editor; the figure reports it.
  const defaults = seriesStyle({}, index, fallback);
  const current = {mode: style.mode ?? defaults.mode, dash: style.dash ?? defaults.line.dash,
    symbol: style.symbol ?? defaults.marker.symbol, color: style.color ?? defaults.line.color,
    width: style.width ?? defaults.line.width, size: style.size ?? defaults.marker.size};
  const change = (property) => (event) => {style[property] = event.target.value; onChange();};
  labelledSelect(container, prefix + "-mode", "Style", [{value: "lines", label: "Lines"}, {value: "markers", label: "Points"}, {value: "lines+markers", label: "Lines + points"}], current.mode, change("mode"));
  const readable = {solid: "Solid", dash: "Dashed", dot: "Dotted", dashdot: "Dash-dot", longdash: "Long dash", longdashdot: "Long dash-dot"};
  labelledSelect(container, prefix + "-dash", "Line type", lineDashChoices.map((value) => ({value, label: readable[value]})), current.dash, change("dash"));
  labelledPlotInput(container, prefix + "-width", "Line width (px)", current.width, "2.2", change("width"), {numeric: true, maxLength: 12});
  labelledSelect(container, prefix + "-symbol", "Point type", markerSymbolChoices.map((value) => ({value, label: value.replaceAll("-", " ").replace(/^./, (letter) => letter.toUpperCase())})), current.symbol, change("symbol"));
  labelledPlotInput(container, prefix + "-size", "Point size (px)", current.size, "6", change("size"), {numeric: true, maxLength: 12});
  const colorLabel = element("label", "plot-color-label", "Color"); colorLabel.htmlFor = prefix + "-color";
  const colorControls = element("span", "plot-color-controls");
  const swatch = element("input"); swatch.type = "color"; swatch.id = prefix + "-swatch";
  swatch.setAttribute("aria-label", "Color picker"); swatch.value = /^#[\da-f]{6}$/i.test(current.color) ? current.color : defaults.line.color;
  const hex = element("input"); hex.type = "text"; hex.id = prefix + "-color"; hex.value = current.color; hex.maxLength = 7;
  hex.spellcheck = false; hex.setAttribute("aria-label", "Color hex value");
  swatch.addEventListener("input", () => {style.color = swatch.value; hex.value = swatch.value; onChange();});
  hex.addEventListener("change", () => {style.color = hex.value.trim(); if (/^#[\da-f]{6}$/i.test(style.color)) swatch.value = style.color; onChange();});
  colorControls.append(swatch, hex); colorLabel.append(colorControls); container.append(colorLabel);
  const reset = element("button", "text-button style-reset", "Reset style"); reset.type = "button";
  reset.addEventListener("click", () => {for (const key of Object.keys(style)) delete style[key]; renderStyleControls(container, style, prefix, index, onChange, fallback); onChange();});
  container.append(reset);
}
function renderPrimaryAppearance(appearance, traces, key) {
  const container = $("profile-settings"), signature = `${key}:${traces.map((trace) => trace.name).join("|")}`;
  if (container.dataset.signature === signature) return;
  container.dataset.signature = signature; container.replaceChildren();
  const axes = element("div"); container.append(axes);
  renderPlotFormat(axes, appearance.format, "profile-format", renderPlot);
  const editor = element("details", "primary-style-editor"); editor.append(element("summary", "", "Series styles"));
  traces.forEach((trace, index) => {
    const row = element("fieldset", "primary-series-style"); row.append(element("legend", "", trace.name));
    const controls = element("div", "series-style-controls"); row.append(controls);
    renderStyleControls(controls, appearance.styles[trace.name] ||= {}, `profile-series-${index}`, index, renderPlot, trace);
    editor.append(row);
  });
  container.append(editor);
}

function renderAxisControls(container, plot, series, axisName, seriesIndex) {
  container.replaceChildren(); const current = series[axisName];
  const dataset = datasetsOf(state.data)[current.dataset];
  const prefix = `plot-${plot.id}-series-${seriesIndex}-${axisName}`;
  const redraw = (property, value) => {
    current[property] = value;
    if (property === "dataset") current.fixed = Math.max(0, ((current.direction === "time" ? datasetsOf(state.data)[value]?.z : datasetsOf(state.data)[value]?.time)?.length || 1) - 1);
    if (property === "direction") current.fixed = Math.max(0, ((value === "time" ? dataset.z : dataset.time)?.length || 1) - 1);
    series[axisName] = normalizeAxis(state.data, current);
    renderAxisControls(container, plot, series, axisName, seriesIndex); renderCustomPlot(plot);
    document.getElementById(`${prefix}-${property}`)?.focus({preventScroll: true});
  };
  container.append(element("strong", "axis-name", axisName.toUpperCase()));
  const controls = element("div", "axis-controls"); container.append(controls);
  labelledSelect(controls, prefix + "-dataset", "Dataset", Object.keys(datasetsOf(state.data)).filter((key) => datasetsOf(state.data)[key]?.fields).map((key) => ({value: key, label: datasetName(key)})), current.dataset, (event) => redraw("dataset", event.target.value));
  labelledSelect(controls, prefix + "-field", "Quantity", vectorOptions(state.data, current.dataset).map((key) => ({value: key, label: key === "Z" ? "Z · Axial position (m)" : key === "TIME" ? "TIME · Time (s)" : `${key}${dataset.fields[key].unit || dataset.fields[key].units ? ` (${dataset.fields[key].unit || dataset.fields[key].units})` : ""}`})), current.field, (event) => redraw("field", event.target.value));
  const coordinate = ["Z", "TIME"].includes(current.field);
  if (!coordinate) {
    labelledSelect(controls, prefix + "-direction", "Vector", [{value: "channel", label: "Along channel"}, {value: "time", label: "Over time"}], current.direction, (event) => redraw("direction", event.target.value));
    const nodes = current.direction === "time";
    labelledSelect(controls, prefix + "-fixed", nodes ? "Node" : "State", (nodes ? dataset.z : dataset.time).map((value, index, values) => ({
      value: index, label: nodes ? `${index + 1} · z = ${numberText(value)} m` : `${index === values.length - 1 ? "Final · " : ""}${pseudoTime(current.dataset, dataset) ? "τ" : "t"} = ${numberText(value)} s`,
    })), current.fixed, (event) => redraw("fixed", Number(event.target.value)));
    try {
      const shape = rectangularShape(dataset.fields[current.field].values).slice(2);
      if (shape.length) {
        labelledSelect(controls, prefix + "-component", shape.length === 1 ? "Component / wall" : "Component indices",
          componentIndices(shape).map((indices) => ({value: JSON.stringify(indices), label: indices.map((value) => value + 1).join(", ")})),
          JSON.stringify(current.component), (event) => redraw("component", JSON.parse(event.target.value)));
      }
    } catch { /* renderCustomPlot reports malformed arrays. */ }
  }
}
function renderSeriesControls(plot) {
  plot.nodes.series.replaceChildren();
  plot.series.forEach((series, index) => {
    const row = element("div", "plot-series");
    const heading = element("div", "series-heading");
    const nameLabel = element("label", "series-name", "Legend label");
    const name = element("input"); name.type = "text"; name.value = series.name; name.placeholder = "Automatic";
    name.id = `plot-${plot.id}-series-${index}-name`; nameLabel.htmlFor = name.id; name.maxLength = 160;
    name.addEventListener("input", () => {series.name = name.value; renderCustomPlot(plot);});
    nameLabel.append(name); heading.append(element("span", "series-number", `Series ${index + 1}`), nameLabel);
    if (plot.series.length > 1) {
      const remove = element("button", "text-button", "Remove series"); remove.type = "button";
      remove.addEventListener("click", () => {plot.series.splice(index, 1); renderSeriesControls(plot); renderCustomPlot(plot);}); heading.append(remove);
    }
    row.append(heading);
    for (const axis of ["x", "y"]) {const container = element("div", "plot-axis"); row.append(container); renderAxisControls(container, plot, series, axis, index);}
    const appearance = element("details", "series-style-editor"); appearance.append(element("summary", "", "Series style"));
    const controls = element("div", "series-style-controls"); appearance.append(controls); row.append(appearance);
    renderStyleControls(controls, series.style ||= {}, `plot-${plot.id}-series-${index}-style`, index, () => renderCustomPlot(plot), {mode: plot.mode || "lines"});
    plot.nodes.series.append(row);
  });
}
function newPlotSeries(data) {
  const dataset = datasetsOf(data).physical ? "physical" : Object.keys(datasetsOf(data))[0];
  const fields = datasetsOf(data)[dataset]?.fields || {};
  const field = fields.U ? "U" : Object.keys(fields)[0];
  return {name: "", style: {}, x: defaultAxis(data, {dataset, field: "Z"}), y: defaultAxis(data, {dataset, field})};
}
function addPlot() {
  const workspace = plotWorkspace();
  if (!workspace || !state.data) return;
  const plot = {id: workspace.nextId++, series: [newPlotSeries(state.data)], legend: false, format: defaultPlotFormat(), nodes: null};
  workspace.plots.push(plot); renderPlotBuilderCards();
  plot.nodes.card.scrollIntoView({block: "start", behavior: "smooth"});
}
function renderPlotBuilderCards() {
  const container = $("custom-plots");
  for (const node of container.querySelectorAll(".custom-plot-canvas")) if (window.Plotly && node.data) Plotly.purge(node);
  container.replaceChildren();
  for (const plot of plotWorkspace()?.plots || []) {
    const card = element("section", "custom-plot-card"); card.id = `plot-card-${plot.id}`;
    const heading = element("div", "panel-heading");
    const title = element("h3", "", `Plot ${plot.id}`); title.id = `plot-title-${plot.id}`; card.setAttribute("aria-labelledby", title.id);
    const actions = element("div", "plot-actions");
    const legend = element("button", "button secondary compact", plot.legend ? "Remove legend" : "Add legend");
    legend.type = "button"; legend.setAttribute("aria-pressed", String(plot.legend));
    legend.addEventListener("click", () => {plot.legend = !plot.legend; legend.textContent = plot.legend ? "Remove legend" : "Add legend"; legend.setAttribute("aria-pressed", String(plot.legend)); renderCustomPlot(plot);});
    const save = element("button", "button secondary compact", "Save PNG"); save.type = "button";
    const remove = element("button", "text-button", "Remove plot"); remove.type = "button";
    remove.addEventListener("click", () => {const workspace = plotWorkspace(); workspace.plots = workspace.plots.filter((item) => item !== plot); renderPlotBuilderCards();});
    actions.append(legend, save, remove); heading.append(title, actions); card.append(heading);
    const editor = element("details", "plot-builder-editor"); editor.open = true;
    editor.append(element("summary", "", "Edit plot"));
    const series = element("div", "plot-series-list"); editor.append(series);
    const footer = element("div", "plot-editor-footer");
    const addSeries = element("button", "button secondary compact", "Add series"); addSeries.type = "button";
    addSeries.addEventListener("click", () => {
      const series = copy(plot.series.at(-1)); series.style ||= {}; delete series.style.color;
      plot.series.push(series); renderSeriesControls(plot); renderCustomPlot(plot);
    });
    footer.append(addSeries);
    editor.append(footer); card.append(editor);
    const appearance = element("div"); card.append(appearance);
    renderPlotFormat(appearance, plot.format ||= defaultPlotFormat(), `plot-${plot.id}-format`, () => renderCustomPlot(plot));
    const error = element("p", "notice error"); error.hidden = true; error.setAttribute("role", "alert");
    const context = element("p", "plot-context"); context.hidden = true;
    const canvas = element("div", "custom-plot-canvas"); canvas.id = `custom-plot-${plot.id}`; canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", `Custom numerical plot ${plot.id}`);
    card.append(error, context, canvas); container.append(card);
    plot.nodes = {card, series, error, context, canvas, save};
    save.addEventListener("click", () => savePlotImage(canvas, `plot-${plot.id}`));
    editor.addEventListener("toggle", () => {if (canvas.data) Plotly.Plots.resize(canvas);});
    renderSeriesControls(plot); renderCustomPlot(plot);
  }
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
  $("download-chart").addEventListener("click", () => savePlotImage($("profile-plot"), "profile"));
  $("profile-legend").addEventListener("click", () => {const workspace = plotWorkspace(); if (workspace) {workspace.primaryLegend = !workspace.primaryLegend; renderPlot();}});
  $("add-plot").addEventListener("click", addPlot);
  window.addEventListener("resize", () => {if (state.data && !$("results-view").hidden) resizePlots();});
}

// These pure adapters are exported only to the dependency-free Node checks.
if (typeof module !== "undefined" && module.exports) module.exports = {inputCaseName, runCaseName, physicalDisplay, primaryQuantityFields, referenceIndexForTime, assertInputDocumentVersion, makeTraces, insideLegend, rectangularShape, componentIndices, defaultAxis, normalizeAxis, outputVector, pairOutputVectors, buildCustomFigure, plotLayout, plotConfig, newPlotSeries, escapePlotText, defaultAxisFormat, defaultPlotFormat, axisLayoutSettings, seriesStyle, applyTraceStyle};
if (typeof document !== "undefined") {
  bindEvents();
  let collapsed = false;
  try { collapsed = localStorage.getItem("openstream-sidebar-collapsed") === "true"; } catch { /* Storage may be disabled. */ }
  setSidebarCollapsed(collapsed); updateRunControls();
  Promise.allSettled([refreshHistory(), api("/api/health").then((health) => {$("app-version").textContent = `Version ${health.version}`; $("app-version").title = `Saved runs: ${health.output_root}`;})]);
}
