"use strict";

// Run with: node --test tests/gui_frontend_logic.test.cjs
// Scientific display checks: unlike DOM snapshots, these guard unit mixing,
// state misalignment, and silent interpretation of unknown input schemas.
const test = require("node:test");
const assert = require("node:assert/strict");
const {inputCaseName, runCaseName, primaryQuantityFields, referenceIndexForTime, assertInputDocumentVersion, makeTraces} = require("../src/openstream/gui_static/app.js");

test("case labels use the original name tag without case normalization", () => {
  const submission = {inputs: {model: {ID: "Run0001"}}};
  const run = {id: "original-run", is_reference: false, changes: [{value: "RUN0001"}]};
  assert.equal(inputCaseName(submission.inputs), "Run0001");
  assert.equal(runCaseName(run, submission), "Run0001");
  assert.equal(run.is_reference, false);
  const anotherEditor = {model: {ID: "Next run"}};
  assert.equal(inputCaseName(anotherEditor), "Next run");
  assert.equal(runCaseName(run, submission), "Run0001");
});

test("case labels preserve Unicode and literal text, with explicit missing-name fallbacks", () => {
  const name = 'ΔP <trial> & "water"';
  assert.equal(inputCaseName({model: {ID: name}}), name);
  assert.equal(inputCaseName({model: {ID: "   "}}), "Unnamed case");
  assert.equal(runCaseName({is_reference: true}), "TUTORIAL1");
  assert.equal(runCaseName({is_reference: false}), "Unnamed case");
  assert.equal(runCaseName({is_reference: false}, {inputs: {model: {ID: {}}}}), "Unnamed case");
});

test("enthalpy and velocity groups exclude derivatives and diagnostic copies", () => {
  const names = ["H", "liquid.H", "vapor.H", "film.H", "drop.H", "film.base.H", "film.wave.H", "MDER.H", "MRM.H", "NEARWALL.H", "U", "vapor.U", "MDER.U", "NEARWALL.U", "aux.film.H"];
  assert.deepEqual(primaryQuantityFields(names, "H"), ["H", "liquid.H", "vapor.H", "film.H", "drop.H", "film.base.H", "film.wave.H"]);
  assert.deepEqual(primaryQuantityFields(names, "U"), ["U", "vapor.U"]);
  assert.deepEqual(primaryQuantityFields(["MDER.W", "MRM.W"], "W"), []);
});

test("reference overlays choose the matching time rather than the native array index", () => {
  const reference = {values: [[10, 11], [20, 21], [30, 31]], unit: "J/kg"};
  const nativeTimes = [0, 0.2], referenceTimes = [0, 0.1, 0.2];
  const matched = referenceIndexForTime(referenceTimes, nativeTimes[1]);
  assert.equal(matched, 2);
  assert.deepEqual(makeTraces(reference, "H", [0, 1], matched, "#000", true)[0].y, [30, 31]);
  assert.equal(referenceIndexForTime(referenceTimes, 0.2 + 5e-13), 2);
  assert.equal(referenceIndexForTime(referenceTimes, 0.2 + 2e-12), -1);
  assert.equal(referenceIndexForTime(referenceTimes, 0.3), -1);
  assert.equal(referenceIndexForTime(undefined, 0.2), -1);
  assert.equal(referenceIndexForTime(referenceTimes, undefined), -1);
});

test("missing reference states are omitted without clamping to a different state", () => {
  const reference = {values: [[10, 11]], unit: "J/kg"};
  assert.deepEqual(makeTraces(reference, "H", [0, 1], -1, "#000", true), []);
  assert.deepEqual(makeTraces(reference, "H", [0, 1], 1, "#000", true), []);
  assert.deepEqual(makeTraces(reference, "H", [0, 1], 20, "#000", true), []);
});

test("individual derivative profiles keep their derivative units", () => {
  const traces = makeTraces({values: [[1, 2]], unit: "J/kg/s"}, "MDER.H", [0, 1], 0, "#000");
  assert.equal(traces.length, 1);
  assert.ok(traces[0].hovertemplate.includes("J/kg/s"));
});

test("input import rejects unknown explicit schema versions", () => {
  assert.doesNotThrow(() => assertInputDocumentVersion({schema: "openstream-gui-input-v1"}));
  assert.doesNotThrow(() => assertInputDocumentVersion({framework: "Mixture"}));
  for (const schema of ["openstream-gui-input-v2", "other-program", "", null, 1]) {
    assert.throws(() => assertInputDocumentVersion({schema}), /Unsupported input schema/);
  }
});
