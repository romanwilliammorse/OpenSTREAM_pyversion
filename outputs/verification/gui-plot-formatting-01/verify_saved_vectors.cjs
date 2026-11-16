"use strict";

// Read-only presentation audit against an actual retained FourField run.
// Run from any directory. An optional output path must not already exist.
// node outputs/verification/gui-plot-formatting-01/verify_saved_vectors.cjs [new-receipt.json]
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../../..");
const {buildCustomFigure, plotLayout, defaultPlotFormat} = require(path.join(root, "src/openstream/gui_static/app.js"));
const sourcePath = "outputs/verification/gui-results-editor-01/fresh/20261115T234316Z-7f724d3d/01-FourField/plot_data.json";
const raw = fs.readFileSync(path.join(root, sourcePath));
const data = JSON.parse(raw);
const original = JSON.stringify(data);
const digest = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
const selected = (dataset, field, component = []) => ({dataset, field, fixed: 0, component, direction: "channel"});
const format = defaultPlotFormat();
format.x = {...format.x, label: "Vapor quality (1)", min: "0", max: "0.8", ticks: "spacing", start: "0", step: "0.2"};
format.y = {...format.y, label: "Liquid mass flow (kg/s)", min: "0", max: "0.04", ticks: "positions", positions: "0,0.02,0.04", labels: "0,0.02,0.04"};
const records = [];
for (const qualityField of ["X", "vapor.X"]) {
  const series = [
    {name: "Base film", x: selected("precursor", qualityField), y: selected("physical", "film.base.W", [0]),
      style: {mode: "lines+markers", dash: "dash", symbol: "square", color: "#d12f3a", width: 3, size: 8}},
    {name: "Wave", x: selected("precursor", qualityField), y: selected("physical", "film.wave.W", [0]),
      style: {mode: "markers", dash: "dot", symbol: "diamond", color: "#3157c4", width: 1.5, size: 6}},
  ];
  const figure = buildCustomFigure(data, {series});
  const layout = plotLayout(figure.xTitle, figure.yTitle, true, "retained-fourfield", format);
  assert.deepEqual(layout.xaxis.range, [0, 0.8]);
  assert.deepEqual(layout.yaxis.range, [0, 0.04]);
  assert.equal(layout.xaxis.dtick, 0.2);
  assert.deepEqual(layout.yaxis.tickvals, [0, 0.02, 0.04]);
  assert.match(layout.font.family, /Times New Roman/);
  for (let index = 0; index < series.length; index++) {
    const expectedX = data.datasets.precursor.fields[qualityField].values[0];
    const expectedY = data.datasets.physical.fields[series[index].y.field].values[0].map(walls => walls[0]);
    const trace = figure.traces[index];
    assert.equal(expectedX.length, 101);
    assert.equal(expectedY.length, 101);
    assert.deepEqual(trace.x, expectedX);
    assert.deepEqual(trace.y, expectedY);
    assert.equal(trace.mode, series[index].style.mode);
    assert.equal(trace.line.color, series[index].style.color);
    assert.equal(trace.marker.color, series[index].style.color);
    assert.equal(trace.line.dash, series[index].style.dash);
    assert.equal(trace.marker.symbol, series[index].style.symbol);
    assert.equal(data.datasets.precursor.fields[qualityField].unit, "1");
    assert.equal(data.datasets.physical.fields[series[index].y.field].unit, "kg/s");
    records.push({x_dataset: "precursor", x: qualityField, x_unit: "1", y_dataset: "physical",
      y: series[index].y.field, y_unit: "kg/s", component_zero_based: [0], pairs: expectedX.length,
      exact_saved_vector_equality: true, style: series[index].style,
      x_sha256_json: digest(JSON.stringify(trace.x)), y_sha256_json: digest(JSON.stringify(trace.y))});
  }
}
assert.equal(JSON.stringify(data), original);
assert.equal(digest(fs.readFileSync(path.join(root, sourcePath))), digest(raw));
const receipt = {schema: "openstream-gui-plot-formatting-vector-audit-v1", passed: true,
  checked_at: new Date().toISOString(), source: sourcePath, source_sha256: digest(raw),
  source_bytes_unchanged: true, data_in_memory_unchanged: true, records,
  scope: "Exact saved-vector fidelity under labels, ranges, ticks and independent series styles/colors; no solver execution or new physical-validation claim."};
const destination = process.argv[2] || path.join(__dirname, `real-vector-invariance-${Date.now()}.json`);
fs.writeFileSync(destination, JSON.stringify(receipt, null, 2) + "\n", {flag: "wx"});
console.log(`Exact ${records.length} cross-stage series / ${records.reduce((sum, record) => sum + record.pairs, 0)} X/Y pairs preserved.`);
