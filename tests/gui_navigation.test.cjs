"use strict";

// Exercise the real asynchronous controllers without a browser dependency.
// Only presentation callbacks and the HTTP boundary are replaced.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../src/openstream/gui_static/app.js"), "utf8");

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return {promise, resolve};
}

function controller(request) {
  const nodes = new Map();
  const notices = [];
  const context = vm.createContext({request, notices});
  // No document during evaluation: the browser startup does not run.
  vm.runInContext(source, context);
  context.document = {
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, {disabled: false, hidden: false});
      return nodes.get(id);
    },
    querySelectorAll() { return []; },
  };
  vm.runInContext(`
    api = request;
    renderEditor = () => {};
    renderRun = () => {};
    showView = () => {};
    showValidation = () => {};
    notice = (message, kind) => notices.push({message, kind});
    refreshHistory = async () => {};
    loadRunData = async () => {};
    schedulePoll = () => {};
  `, context);
  return {
    nodes, notices,
    run: (code) => vm.runInContext(code, context),
    value: (code) => JSON.parse(vm.runInContext(`JSON.stringify(${code})`, context)),
  };
}

test("Run validates and submits the same captured model and case despite subsequent editor changes", async () => {
  const validation = deferred();
  const requests = [];
  const app = controller(async (url, options) => {
    requests.push({url, body: JSON.parse(options.body)});
    if (url === "/api/validate") return validation.promise;
    if (url === "/api/runs") return {id: "new-run", framework: "Mixture", status: "queued"};
    throw new Error(`Unexpected request ${url}`);
  });
  app.run('state.framework = "Mixture"; state.inputs = {model: {ID: "Run0001", NNODES: 100}};');
  const running = app.run("startRun()");
  assert.equal(app.nodes.get("run-case").disabled, true);
  assert.equal(app.nodes.get("framework").disabled, true);
  assert.equal(app.nodes.get("load-inputs").disabled, true);
  // A second click must not start another validation or submission.
  await app.run("startRun()");
  assert.equal(requests.length, 1);
  app.run('state.inputs.model.ID = "LaterEdit"; state.framework = "FourField";');
  validation.resolve({valid: true, is_reference: false});
  await running;
  assert.deepEqual(requests.map(({url}) => url), ["/api/validate", "/api/runs"]);
  assert.deepEqual(requests[1].body, requests[0].body);
  assert.equal(requests[1].body.framework, "Mixture");
  assert.equal(requests[1].body.inputs.model.ID, "Run0001");
  assert.equal(app.value('savedInputs.get("new-run").inputs.model.ID'), "Run0001");
  assert.equal(app.value("state.submitting"), false);
  assert.deepEqual(app.notices.filter(({kind}) => kind === "error"), []);
});

test("a stale history model load cannot overwrite a newer selection or unlock Run early", async () => {
  const oldSchema = deferred(), oldBaseline = deferred(), newStatus = deferred();
  const oldLoadStarted = deferred();
  const app = controller(async (url) => {
    if (url === "/api/runs/old") return {id: "old", framework: "Mixture", status: "completed"};
    if (url === "/api/schema?framework=Mixture") { oldLoadStarted.resolve(); return oldSchema.promise; }
    if (url === "/api/baseline/Mixture") return oldBaseline.promise;
    if (url === "/api/runs/new") return newStatus.promise;
    if (url === "/api/schema?framework=FourField") return {fields: []};
    if (url === "/api/baseline/FourField") return {inputs: {model: {ID: "TUTORIAL1"}}};
    throw new Error(`Unexpected request ${url}`);
  });
  app.run(`
    state.framework = "TwoFluid"; state.inputs = {model: {ID: "Original"}};
    savedInputs.set("old", {framework: "Mixture", inputs: {model: {ID: "OldCase"}}});
    savedInputs.set("new", {framework: "FourField", inputs: {model: {ID: "Run0001"}}});
  `);
  const oldSelection = app.run('selectRun("old")');
  await oldLoadStarted.promise;
  const newSelection = app.run('selectRun("new")');
  oldSchema.resolve({fields: []});
  oldBaseline.resolve({inputs: {model: {ID: "TUTORIAL1"}}});
  await oldSelection;
  assert.equal(app.value("state.inputs.model.ID"), "Original");
  assert.equal(app.value("state.framework"), "TwoFluid");
  assert.equal(app.value("state.loading"), true);
  assert.equal(app.nodes.get("run-case").disabled, true);
  newStatus.resolve({id: "new", framework: "FourField", status: "completed"});
  await newSelection;
  assert.equal(app.value("state.inputs.model.ID"), "Run0001");
  assert.equal(app.value("state.framework"), "FourField");
  assert.equal(app.value("state.selectedRun.id"), "new");
  assert.equal(app.value("state.loading"), false);
  assert.equal(app.nodes.get("run-case").disabled, false);
  assert.deepEqual(app.notices.filter(({kind}) => kind === "error"), []);
});
