"use strict";

// Run with: node --test tests/gui_frontend_logic.test.cjs
// Scientific display checks: unlike DOM snapshots, these guard unit mixing,
// state misalignment, and silent interpretation of unknown input schemas.
const test = require("node:test");
const assert = require("node:assert/strict");
const {inputCaseName, runCaseName, physicalDisplay, primaryQuantityFields, referenceIndexForTime, assertInputDocumentVersion, makeTraces} = require("../src/openstream/gui_static/app.js");

test("historical annular area flags display as informational without rewriting evidence", () => {
  const physical = {status: "failed", diagnostics: {physical_consistency: false,
    area_closure_relative_tolerance: 1e-6, max_unblended_annular_area_closure_relative: .1124,
    inventory_by_time: [{time_s: 0}]}};
  const original = JSON.stringify(physical);
  for (const framework of ["ThreeField", "FourField"]) {
    const shown = physicalDisplay({framework, physical});
    assert.equal(shown.status, "informational");
    assert.equal(shown.historicalAreaOnly, true);
    assert.strictEqual(shown.diagnostics, physical.diagnostics);
  }
  assert.equal(JSON.stringify(physical), original);
  for (const framework of ["Mixture", "TwoFluid"]) assert.strictEqual(physicalDisplay({framework, physical}), physical);
});

test("annular display preserves unrelated failures and never invents a physical pass", () => {
  const unknown = {status: "failed", diagnostics: {physical_consistency: false}};
  assert.strictEqual(physicalDisplay({framework: "FourField", physical: unknown}), unknown);
  const current = {status: "not_checked", diagnostics: {phase_volume_closure_role: "informational", physical_consistency: null}};
  assert.equal(physicalDisplay({framework: "FourField", physical: current}).status, "informational");
  const independent = {...current, status: "failed"};
  assert.strictEqual(physicalDisplay({framework: "FourField", physical: independent}), independent);
});

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
const {
  insideLegend, rectangularShape, componentIndices, defaultAxis, normalizeAxis,
  outputVector, pairOutputVectors, buildCustomFigure, plotLayout, plotConfig, newPlotSeries,
} = require("../src/openstream/gui_static/app.js");

function vectorFixture() {
  return {datasets: {
    physical: {z: [0, 0.5, 1], time: [0, 2], time_label: "Physical time [s]", fields: {
      "film.U": {unit: "m/s", values: [[[1, 10], [2, 20], [3, 30]], [[4, 40], [5, 50], [6, 60]]]},
      P: {unit: "Pa", values: [[100, 90, 80], [110, 95, 85]]},
      "ITR.DU": {unit: "m/s", values: [[null, 0.1, 0.2], [null, 0.3, 0.4]]},
    }},
    precursor: {z: [0, 0.5, 1], time: [0], time_label: "Mixture precursor physical time [s]", fields: {
      "vapor.X": {unit: "1", values: [[0.2, 0.5, 0.8]]},
      U: {unit: "m/s", values: [[8, 9, 10]]},
    }},
    precursor_initialization: {z: [0, 0.5, 1], time: [0, 1, 2], time_label: "Mixture precursor initialization pseudo-time [s]", fields: {
      U: {unit: "m/s", values: [[0, 1, 2], [1, 2, 3], [3, 4, 5]]},
    }},
  }};
}
const axis = (dataset, field, fixed = 0, component = [], direction = "channel") => ({dataset, field, fixed, component, direction});

test("cross-dataset quality versus film velocity uses exact components and does not mutate output", () => {
  const data = vectorFixture(), frozen = JSON.stringify(data);
  const pair = pairOutputVectors(data, axis("precursor", "vapor.X"), axis("physical", "film.U", 0, [1]));
  assert.deepEqual(pair.x.values, [0.2, 0.5, 0.8]);
  assert.deepEqual(pair.y.values, [10, 20, 30]);
  assert.equal(pair.x.unit, "1"); assert.equal(pair.y.unit, "m/s");
  assert.deepEqual(pair.notes, []);
  pair.x.values[0] = 99;
  assert.equal(JSON.stringify(data), frozen);
});

test("time histories preserve the selected node and component rather than flattening cells", () => {
  const data = vectorFixture();
  const vector = outputVector(data, axis("physical", "film.U", 1, [1], "time"));
  assert.deepEqual(vector.values, [20, 50]);
  assert.deepEqual(vector.coordinates, [0, 2]);
  assert.equal(vector.fixedValue, 0.5);
  const time = outputVector(data, axis("physical", "TIME"));
  assert.deepEqual(time.values, [0, 2]);
  assert.equal(time.unit, "s");
});

test("vector-length mismatches reject without truncation or interpolation", () => {
  assert.throws(() => pairOutputVectors(vectorFixture(), axis("physical", "TIME"), axis("physical", "P")), /X has 2 values; Y has 3/);
});

test("equal-length but different coordinates or dimensions are explicitly paired by index", () => {
  const data = vectorFixture();
  data.datasets.precursor.z = [0, 0.6, 1.2];
  const pair = pairOutputVectors(data, axis("precursor", "vapor.X"), axis("physical", "P"));
  assert.deepEqual(pair.x.values, [0.2, 0.5, 0.8]);
  assert.match(pair.notes.join(" "), /Paired by index/);
  const mixed = pairOutputVectors(data, axis("precursor_initialization", "TIME"), axis("physical", "Z"));
  assert.match(mixed.notes.join(" "), /different coordinates/);
  assert.match(mixed.notes.join(" "), /pseudo-time/);
});

test("different states and initialization pseudo-time remain disclosed", () => {
  const pair = pairOutputVectors(vectorFixture(), axis("precursor", "U"), axis("physical", "film.U", 1, [0]));
  assert.match(pair.notes.join(" "), /different fixed states/);
  const init = outputVector(vectorFixture(), axis("precursor_initialization", "TIME"));
  assert.equal(init.label, "Initialization pseudo-time");
  assert.equal(init.pseudo, true);
});

test("null diagnostics remain gaps and cannot be presented as zero or joined", () => {
  const data = vectorFixture();
  const series = {name: "Diagnostic", x: axis("physical", "Z"), y: axis("physical", "ITR.DU", 1)};
  const figure = buildCustomFigure(data, {series: [series], mode: "lines"});
  assert.deepEqual(figure.traces[0].y, [null, 0.3, 0.4]);
  assert.equal(figure.traces[0].connectgaps, false);
  assert.match(figure.notes.join(" "), /gaps/);
  data.datasets.physical.fields["ITR.DU"].values[1] = [null, null, null];
  assert.throws(() => buildCustomFigure(data, {series: [series]}), /no finite X\/Y pairs/);
});

test("multi-series axes require matching recorded units without implicit unit conversion", () => {
  const data = vectorFixture();
  const first = {name: "Film", x: axis("physical", "Z"), y: axis("physical", "film.U", 0, [0])};
  const second = {name: "Precursor", x: axis("precursor", "Z"), y: axis("precursor", "U")};
  const figure = buildCustomFigure(data, {series: [first, second]});
  assert.equal(figure.traces.length, 2);
  assert.equal(figure.yTitle, "Y (m/s)");
  assert.equal(figure.xTitle, "Axial position, z (m)");
  second.y = axis("physical", "P");
  assert.throws(() => buildCustomFigure(data, {series: [first, second]}), /same recorded X units and Y units/);
});

test("unknown units are labeled unavailable rather than invented or declared dimensionless", () => {
  const data = vectorFixture();
  delete data.datasets.physical.fields.P.unit;
  const figure = buildCustomFigure(data, {series: [{name: "", x: axis("physical", "Z"), y: axis("physical", "P")}]});
  assert.equal(figure.yTitle, "P (unit unavailable)");
});

test("malformed arrays and out-of-range selection fail explicitly", () => {
  const data = vectorFixture();
  assert.throws(() => outputVector(data, axis("physical", "film.U", 0)), /one valid component/);
  assert.throws(() => outputVector(data, axis("physical", "film.U", 0, [2])), /one valid component/);
  assert.throws(() => outputVector(data, axis("physical", "P", 3)), /state or node is unavailable/);
  data.datasets.physical.fields.P.values[1] = [1, 2];
  assert.throws(() => outputVector(data, axis("physical", "P")), /inconsistent array dimensions/);
  assert.throws(() => rectangularShape([[1], ["bad"]] ), /nonnumeric/);
  assert.throws(() => rectangularShape([]), /empty dimension/);
});

test("arbitrary trailing component dimensions remain explicit", () => {
  const data = {datasets: {physical: {z: [0, 1], time: [0], fields: {
    tensor: {unit: "1", values: [[[[1, 2], [3, 4]], [[5, 6], [7, 8]]]]},
  }}}};
  assert.deepEqual(componentIndices([2, 2]), [[0, 0], [0, 1], [1, 0], [1, 1]]);
  assert.deepEqual(outputVector(data, axis("physical", "tensor", 0, [1, 0])).values, [3, 7]);
});

test("new figures and axis defaults have independent selections", () => {
  const data = vectorFixture(), first = newPlotSeries(data), second = newPlotSeries(data);
  first.x.dataset = "precursor";
  first.y.component.push(99);
  assert.equal(second.x.dataset, "physical");
  assert.deepEqual(second.y.component, [0]);
  const configured = defaultAxis(data, {dataset: "precursor_initialization", field: "U"});
  assert.equal(configured.fixed, 2);
  assert.equal(normalizeAxis(data, {...configured, field: "TIME"}).direction, "time");
  const history = defaultAxis(data, {dataset: "physical", field: "P", direction: "time"});
  assert.equal(history.fixed, data.datasets.physical.z.length - 1);
  assert.deepEqual(outputVector(data, history).values, data.datasets.physical.fields.P.values.map((row) => row.at(-1)));
});

test("legend is inside the upper-left plot area and cloud upload is disabled", () => {
  const legend = insideLegend();
  assert.ok(legend.x > 0 && legend.x < 1 && legend.y > 0 && legend.y < 1);
  assert.equal(legend.xanchor, "left"); assert.equal(legend.yanchor, "top");
  assert.equal(legend.xref, "paper"); assert.equal(legend.yref, "paper");
  assert.equal(plotLayout("X", "Y", false, "a").showlegend, false);
  assert.equal(plotLayout("X", "Y", true, "b").showlegend, true);
  assert.equal(plotLayout("X", "Y", true, "b").title, undefined);
  assert.equal(plotConfig("figure").showSendToCloud, false);
  assert.ok(plotConfig("figure").modeBarButtonsToRemove.includes("sendDataToCloud"));
});
