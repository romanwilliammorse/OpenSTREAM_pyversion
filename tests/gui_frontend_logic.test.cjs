"use strict";

// Run with: node --test tests/gui_frontend_logic.test.cjs
// Scientific display checks: unlike DOM snapshots, these guard unit mixing,
// state misalignment, and silent interpretation of unknown input schemas.
const test = require("node:test");
const assert = require("node:assert/strict");
const {inputCaseName, runCaseName, physicalDisplay, primaryQuantityFields, referenceIndexForTime, assertInputDocumentVersion, makeTraces} = require("../src/openstream/gui_static/app.js");
const {referenceEnabled, referenceSource, referencePresentation, referenceOverlay} = require("../src/openstream/gui_static/app.js");

test("manuscript labels distinguish author attribution from the actual immutable archive", () => {
  for (const framework of ["ThreeField", "FourField"]) {
    const run = {framework, is_reference: true, changes: [], change_count: 0,
      reference: {status: "passed", archive: {file: `tutorial1_${framework}Solver.mat`}}};
    const original = JSON.stringify(run);
    const shown = referencePresentation(run);
    assert.equal(shown.label, 'Referenced against “Le Corre 2025”');
    assert.equal(shown.result, "Profiles agree");
    assert.equal(shown.enabled, true);
    assert.match(shown.detail, /NURETH-21 \(2025\), Figures 3–4/);
    assert.match(shown.detail, /Numerical target: OpenSTREAM TUTORIAL1 archive/);
    assert.match(shown.detail, /published curves remains unverified/);
    assert.equal(JSON.stringify(run), original);
  }
  for (const framework of ["Mixture", "TwoFluid"]) {
    assert.equal(referenceSource({framework}).label, "OpenSTREAM TUTORIAL1");
    assert.equal(referenceSource({framework}).citation, null);
  }
});

test("changed or unassessed saved inputs suppress comparison cards and legacy reference overlays", () => {
  const dataset = {z: [0, 1], reference_time: [0], reference_fields: {W: {values: [[1, 2]]}}};
  const original = JSON.stringify(dataset);
  for (const run of [undefined, {}, {is_reference: false, reference: {status: "passed"}},
    {is_reference: true, changes: [{key: "POWER", value: 1}]}, {is_reference: true, change_count: 1}]) {
    assert.equal(referenceEnabled(run), false);
    assert.equal(referencePresentation(run).enabled, false);
    assert.equal(referenceOverlay(dataset, run, 0), null);
  }
  const run = {framework: "FourField", is_reference: true};
  const overlay = referenceOverlay(dataset, run, 0);
  assert.equal(overlay.label, "Le Corre 2025");
  assert.strictEqual(overlay.fields, dataset.reference_fields);
  assert.equal(overlay.timeIndex, 0);
  assert.equal(referenceOverlay(dataset, run, 2).timeIndex, -1);
  assert.equal(JSON.stringify(dataset), original);
  const trace = makeTraces({values: [[1, 2]], unit: "kg/s"}, "film.W", [0, 1], 0, "#000", true, overlay.label)[0];
  assert.equal(trace.name, "Film · Le Corre 2025");
  assert.deepEqual(trace.y, [1, 2]);
});

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

const {
  defaultAxisFormat, defaultPlotFormat, axisLayoutSettings, seriesStyle,
  escapePlotText, applyTraceStyle,
} = require("../src/openstream/gui_static/app.js");

test("all GUI figures inherit Times New Roman without adding a figure title", () => {
  const layout = plotLayout("X (1)", "Film flow (kg/s)", true, "run:plot");
  assert.match(layout.font.family, /^['"]?Times New Roman['"]?(,|$)/);
  for (const font of [layout.legend.font, layout.xaxis.tickfont, layout.yaxis.tickfont,
    layout.xaxis.title.font, layout.yaxis.title.font, layout.hoverlabel?.font]) {
    if (font?.family) assert.equal(font.family, layout.font.family);
  }
  assert.equal(layout.title, undefined);
});

test("blank axis formatting restores automatic limits and quantity-based labels", () => {
  const axis = axisLayoutSettings(defaultAxisFormat(), "Quality (1)", "X");
  assert.equal(axis.autorange, true);
  assert.equal(axis.range, undefined);
  assert.equal(axis.title.text, "Quality (1)");
  assert.equal(axis.tickmode, "auto");
  assert.equal(axis.tickvals, null);
  assert.equal(axis.dtick, null);
  assert.equal(axis.ticks, "outside");
});

test("manual limits preserve zero, negative values and scientific notation exactly", () => {
  const input = {...defaultAxisFormat(), min: "0", max: "8e-1", label: "Vapor quality, x (1)"};
  const frozen = JSON.stringify(input);
  const x = axisLayoutSettings(input, "unused", "X");
  assert.equal(x.autorange, false);
  assert.deepEqual(x.range, [0, 0.8]);
  assert.equal(x.title.text, input.label);
  assert.equal(JSON.stringify(input), frozen);
  const y = axisLayoutSettings({...defaultAxisFormat(), min: "-2.5e3", max: "1e4"}, "Pressure (Pa)", "Y");
  assert.deepEqual(y.range, [-2500, 10000]);
});

test("invalid or incomplete limits fail instead of coercing to a plausible view", () => {
  for (const [min, max] of [["1", "1"], ["2", "1"], ["NaN", "2"], ["0", "Infinity"],
    ["garbage", "1"], ["0", "1e999"], ["-1e308", "1e308"], ["0", ""], ["", "1"]]) {
    assert.throws(() => axisLayoutSettings({...defaultAxisFormat(), min, max}, "X", "X"));
  }
});

test("regular ticks use an explicit origin and positive spacing in recorded axis units", () => {
  const x = axisLayoutSettings({...defaultAxisFormat(), ticks: "spacing", start: "-0.2", step: "1e-1"}, "Quality (1)", "X");
  assert.equal(x.tickmode, "linear");
  assert.equal(x.tick0, -0.2);
  assert.equal(x.dtick, 0.1);
  assert.equal(x.tickvals, null);
  for (const step of ["0", "-0.1", "", "NaN", "Infinity", "1e999", "not a number"]) {
    assert.throws(() => axisLayoutSettings({...defaultAxisFormat(), ticks: "spacing", start: "0", step}, "X", "X"));
  }
  assert.throws(() => axisLayoutSettings({...defaultAxisFormat(), ticks: "spacing", start: "bad", step: "1"}, "X", "X"));
});

test("explicit tick positions and labels remain paired without resampling data", () => {
  const input = {...defaultAxisFormat(), ticks: "positions", positions: "0, 0.25, 0.8", labels: "inlet, midpoint, outlet"};
  const frozen = JSON.stringify(input);
  const x = axisLayoutSettings(input, "X", "X");
  assert.equal(x.tickmode, "array");
  assert.deepEqual(x.tickvals, [0, 0.25, 0.8]);
  assert.deepEqual(x.ticktext, ["inlet", "midpoint", "outlet"]);
  assert.equal(JSON.stringify(input), frozen);
  const numeric = axisLayoutSettings({...input, labels: ""}, "X", "X");
  assert.equal(numeric.ticktext, null);
  for (const positions of ["", "0,NaN,1", "0,Infinity", "0,,1", "0,one,1", "0,1,1", "1,0"]) {
    assert.throws(() => axisLayoutSettings({...input, positions, labels: ""}, "X", "X"));
  }
  assert.throws(() => axisLayoutSettings({...input, labels: "one, two"}, "X", "X"));
});

test("user axis and tick labels remain literal text rather than Plotly markup", () => {
  const input = {...defaultAxisFormat(), label: '<b>Quality</b> & "x"', ticks: "positions",
    positions: "0,1", labels: "<i>inlet</i>,A&B"};
  const x = axisLayoutSettings(input, "X", "X");
  assert.equal(x.title.text, '&lt;b&gt;Quality&lt;/b&gt; &amp; "x"');
  assert.deepEqual(x.ticktext, ["&lt;i&gt;inlet&lt;/i&gt;", "A&amp;B"]);
  assert.equal(escapePlotText("ΔP < 0 & x > 0"), "ΔP &lt; 0 &amp; x &gt; 0");
});

test("formatting is independent between axes and figures and resets the zoom revision", () => {
  const first = defaultPlotFormat(), second = defaultPlotFormat();
  first.x.min = "0"; first.x.max = "1"; first.x.label = "First X";
  assert.deepEqual(first.y, defaultAxisFormat());
  assert.deepEqual(second, defaultPlotFormat());
  const original = plotLayout("X", "Y", false, "run:plot", second);
  const limited = plotLayout("X", "Y", false, "run:plot", first);
  assert.notEqual(limited.uirevision, original.uirevision);
  assert.deepEqual(limited.xaxis.range, [0, 1]);
  assert.equal(limited.yaxis.autorange, true);
  const reset = defaultPlotFormat(); reset.revision = 1;
  const restored = plotLayout("X", "Y", false, "run:plot", reset);
  assert.notEqual(restored.uirevision, original.uirevision);
  assert.equal(restored.xaxis.autorange, true);
  assert.equal(restored.xaxis.range, undefined);
});

test("each series has its own line, marker and color styles", () => {
  const first = seriesStyle({mode: "lines+markers", dash: "dash", symbol: "square", color: "#ff0000", width: 3, size: 8}, 0);
  const second = seriesStyle({mode: "markers", dash: "dot", symbol: "diamond", color: "#0000ff", width: 1, size: 5}, 1);
  assert.equal(first.mode, "lines+markers");
  assert.equal(first.line.dash, "dash"); assert.equal(first.line.width, 3);
  assert.equal(first.marker.symbol, "square"); assert.equal(first.marker.size, 8);
  assert.equal(first.line.color, "#ff0000"); assert.equal(first.marker.color, "#ff0000");
  assert.equal(second.mode, "markers");
  assert.equal(second.marker.symbol, "diamond"); assert.equal(second.marker.size, 5);
  assert.equal(second.line.color, "#0000ff"); assert.equal(second.marker.color, "#0000ff");
  first.line.color = "#00ff00";
  assert.equal(second.line.color, "#0000ff");
  assert.notEqual(seriesStyle({}, 0).line.color, seriesStyle({}, 1).line.color);
});

test("unknown line and marker styles, invalid colors and invalid sizes reject", () => {
  for (const invalid of [{mode: "splines"}, {dash: "invented"}, {symbol: "invented"},
    {color: "not-a-color"}, {color: "url(https://example.com/image)"},
    {width: -1}, {width: Infinity}, {size: -1}, {size: NaN}]) {
    assert.throws(() => seriesStyle(invalid, 0));
  }
});

test("style overrides preserve native and reference trace data, hover units and gaps", () => {
  const field = {values: [[1, null, 3]], unit: "kg/s"};
  const reference = makeTraces(field, "film.W", [0, 0.5, 1], 0, "#123456", true)[0];
  const frozen = JSON.stringify(reference);
  const automatic = applyTraceStyle(reference, {}, 0);
  assert.equal(automatic.line.dash, "dot");
  assert.equal(automatic.line.width, 1.6);
  assert.equal(automatic.line.color, "#123456");
  const styled = applyTraceStyle(reference, {mode: "markers", symbol: "square", color: "#ff0000"}, 0);
  assert.deepEqual(styled.x, [0, 0.5, 1]);
  assert.deepEqual(styled.y, [1, null, 3]);
  assert.equal(styled.connectgaps, false);
  assert.equal(styled.hovertemplate, reference.hovertemplate);
  assert.equal(styled.name, reference.name);
  assert.equal(JSON.stringify(reference), frozen);
});

test("cross-stage multi-series formatting leaves stored numerical arrays and units unchanged", () => {
  const data = vectorFixture(), frozen = JSON.stringify(data);
  const first = {name: "Film", x: axis("precursor", "vapor.X"), y: axis("physical", "film.U", 0, [0]),
    style: {mode: "lines+markers", dash: "dash", symbol: "square", color: "#ff0000"}};
  const second = {name: "Precursor", x: axis("precursor", "vapor.X"), y: axis("precursor", "U"),
    style: {mode: "markers", symbol: "diamond", color: "#0000ff"}};
  const figure = buildCustomFigure(data, {series: [first, second]});
  assert.deepEqual(figure.traces.map(trace => trace.x), [[0.2, 0.5, 0.8], [0.2, 0.5, 0.8]]);
  assert.deepEqual(figure.traces.map(trace => trace.y), [[1, 2, 3], [8, 9, 10]]);
  assert.equal(figure.traces[0].mode, "lines+markers");
  assert.equal(figure.traces[0].line.dash, "dash");
  assert.equal(figure.traces[0].marker.symbol, "square");
  assert.equal(figure.traces[0].line.color, "#ff0000");
  assert.equal(figure.traces[1].mode, "markers");
  assert.equal(figure.traces[1].marker.symbol, "diamond");
  assert.equal(figure.traces[1].marker.color, "#0000ff");
  assert.equal(figure.yTitle, "Y (m/s)");
  assert.match(figure.traces[0].hovertemplate, /m\/s/);
  assert.equal(JSON.stringify(data), frozen);
  const independent = newPlotSeries(data), another = newPlotSeries(data);
  independent.style.color = "#ff0000";
  assert.equal(another.style.color, undefined);
});
