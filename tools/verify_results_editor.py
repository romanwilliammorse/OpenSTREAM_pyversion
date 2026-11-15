"""Compare read-only CSV/vector endpoints with retained original run artifacts.

No solver is started and no saved run is modified. Every exported scalar and
plot vector is checked, including coordinate/component indices and nonfinite
diagnostics. Credentials stay in memory and are omitted from receipts.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import getpass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
CASES = (
    ("Mixture", "47b8e605097f476db27a6869e551b037"),
    ("TwoFluid", "31bdc0a96f194ec1a3dac210568e4b28"),
    ("ThreeField", "8b87b512f1594e08a6d59082e4de90a8"),
    ("FourField", "56c656bbe0bd4f6e908c190ab26d1f83"),
)
DATASETS = {
    "physical": ("results.npz", "physical"),
    "initialization": ("initialization.npz", "pseudo"),
    "precursor": ("mixture/results.npz", "physical"),
    "precursor_initialization": ("mixture/initialization.npz", "pseudo"),
}
KINDS = ("inputs", "boundary-conditions", "geometry", "results")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def csv_rows(body):
    return csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""))


def shape_and_leaves(value, prefix=()):
    if not isinstance(value, list):
        return [], [(prefix, value)]
    if not value:
        return [0], [(prefix, value)]
    children = [shape_and_leaves(item, prefix + (index,)) for index, item in enumerate(value)]
    require(all(child[0] == children[0][0] for child in children), "Ragged saved input")
    return [len(value)] + children[0][0], [leaf for child in children for leaf in child[1]]


def displayed_text(value):
    value = str(value)
    needs_quote = bool(value) and (value[0] in "\t\r\n" or value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")))
    return "'" + value if needs_quote else value


def check_input_csv(body, kind, payload, unit_metadata):
    groups = {"inputs": ("model", "options"), "boundary-conditions": ("bc",), "geometry": ("geometry",)}[kind]
    expected = {}
    for group in groups:
        records = payload["inputs"][group] if group == "bc" else [payload["inputs"][group]]
        for record_index, record in enumerate(records):
            for name, value in record.items():
                shape, leaves = shape_and_leaves(value)
                for index, scalar in leaves:
                    expected[(group, record_index, name, index)] = (shape, scalar, unit_metadata[group][name]["unit"])
    seen = set()
    for row in csv_rows(body):
        key = (row["section"], int(row["record_index"]), row["parameter"], tuple(json.loads(row["element_indices"])))
        require(key in expected, "Unexpected input CSV element")
        require(key not in seen, "Duplicate input CSV element")
        seen.add(key)
        shape, value, unit = expected[key]
        actual = json.loads(row["value_json"])
        require(type(actual) is type(value) and actual == value, "Input CSV changed a saved value or JSON type")
        require(json.loads(row["shape"]) == shape, "Input CSV shape differs")
        require(row["unit"] == displayed_text(unit), "Input CSV units differ")
    require(seen == set(expected), "Input CSV omitted saved elements")
    return len(seen)


def load_arrays(output):
    datasets = {}
    for name, (relative, time_kind) in DATASETS.items():
        filename = output / relative
        if not filename.is_file():
            continue
        metadata = json.loads((filename.parent / "metadata.json").read_text(encoding="utf-8"))
        with np.load(filename, allow_pickle=False) as archive:
            datasets[name] = {"arrays": {key: archive[key].copy() for key in archive.files},
                              "units": metadata["units"], "time_kind": time_kind}
    return datasets


def same_number(text, value):
    if isinstance(value, (bool, np.bool_)):
        return text == ("true" if value else "false")
    if np.issubdtype(type(value), np.integer):
        try:
            return int(text) == int(value)
        except ValueError:
            return False
    try:
        actual, expected = float(text), float(value)
    except ValueError:
        return False
    if math.isnan(expected):
        return math.isnan(actual)
    return actual == expected and (expected != 0 or np.signbit(actual) == np.signbit(expected))


def check_results_csv(body, datasets):
    seen = set()
    expected_count = sum(array.size for data in datasets.values() for array in data["arrays"].values())
    nonfinite = 0
    for row in csv_rows(body):
        dataset, name = row["dataset"], row["quantity"]
        require(dataset in datasets and name in datasets[dataset]["arrays"], "Unexpected results CSV array")
        data = datasets[dataset]
        arrays = data["arrays"]
        array = arrays[name]
        index = tuple(json.loads(row["array_indices"]))
        key = (dataset, name, index)
        require(key not in seen, "Duplicate results CSV element")
        require(len(index) == array.ndim and all(type(i) is int and 0 <= i < size for i, size in zip(index, array.shape)), "Invalid results CSV index")
        seen.add(key)
        expected = array[index]
        require(same_number(row["value"], expected), "Results CSV changed a stored scalar")
        nonfinite += int(not np.isfinite(expected))
        require(json.loads(row["array_shape"]) == list(array.shape), "Results CSV array shape differs")
        require(row["dtype"] == str(array.dtype), "Results CSV dtype differs")
        require(row["time_kind"] == data["time_kind"], "Results CSV time role differs")
        unit = data["units"].get(name, "m" if name == "Z" else "s" if name == "TIME" else "")
        require(row["unit"] == displayed_text(unit), "Results CSV units differ")
        z, time = arrays["Z"], arrays["TIME"]
        aligned = array.ndim >= 2 and array.shape[:2] == (len(time), len(z))
        ti = index[0] if name == "TIME" or aligned else None
        zi = index[1] if aligned else index[0] if name == "Z" else None
        require(row["time_index"] == ("" if ti is None else str(ti)), "CSV time index differs")
        require(row["node_index"] == ("" if zi is None else str(zi)), "CSV node index differs")
        require(json.loads(row["component_indices"]) == (list(index[2:]) if aligned else []), "CSV component indices differ")
        require(row["time_s"] == "" if ti is None else same_number(row["time_s"], time[ti]), "CSV time coordinate differs")
        require(row["z_m"] == "" if zi is None else same_number(row["z_m"], z[zi]), "CSV axial coordinate differs")
    require(len(seen) == expected_count, "Results CSV omitted stored numeric elements")
    return {"elements": len(seen), "nonfinite_diagnostics_preserved": nonfinite}


def check_plot_data(body, datasets):
    data = json.loads(body)
    require(set(data["datasets"]) == set(datasets), "Plot data omitted or added a stored dataset")
    field_count, scalar_count, gaps = 0, 0, 0
    for name, expected in datasets.items():
        actual = data["datasets"][name]
        arrays = expected["arrays"]
        require(actual["z"] == arrays["Z"].tolist() and actual["time"] == arrays["TIME"].tolist(), "Plot coordinates differ")
        require(set(actual["fields"]) == set(arrays) - {"Z", "TIME"}, "Plot fields differ")
        require(("pseudo-time" in actual["time_label"]) == (expected["time_kind"] == "pseudo"), "Plot time role differs")
        for field, value in actual["fields"].items():
            array = arrays[field]
            shape, leaves = shape_and_leaves(value["values"])
            require(shape == list(array.shape), "Plot vector shape differs")
            require(value["unit"] == expected["units"].get(field, "") and value["units"] == value["unit"], "Plot units differ")
            for index, scalar in leaves:
                original = array[index]
                if np.isfinite(original):
                    require(scalar is not None and scalar == original, "Plot scalar differs from saved result")
                else:
                    require(scalar is None, "Nonfinite plot value was not retained as a gap")
                    gaps += 1
                scalar_count += 1
            field_count += 1
    return {"datasets": len(datasets), "fields": field_count, "elements": scalar_count, "nonfinite_gaps": gaps}


class LocalReader:
    def __init__(self, origin):
        from verify_hosted_gui import SameOriginRedirects
        self.origin = origin
        self.opener = urllib.request.build_opener(SameOriginRedirects(origin))

    def request(self, method, path):
        require(method == "GET", "Local verification is read-only")
        try:
            response = self.opener.open(self.origin + path, timeout=120)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(256 * 1024 * 1024 + 1)
            require(len(body) <= 256 * 1024 * 1024, "Verification response too large")
            return response.code, body, None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="https://openstream-py.vercel.app")
    parser.add_argument("--output", type=Path, required=True, help="Parent folder; a fresh dated subfolder is created")
    parser.add_argument("--reference-root", type=Path, default=ROOT / "outputs/verification/hosted-http/20261115T175731Z-a0e1560b")
    parser.add_argument("--save-csv", action="store_true", help="Also preserve exact downloaded CSV bytes")
    args = parser.parse_args(argv)
    parsed = urllib.parse.urlsplit(args.origin)
    require(parsed.scheme in ("http", "https") and bool(parsed.hostname) and not parsed.username and not parsed.password
            and parsed.path in ("", "/") and not parsed.query and not parsed.fragment, "Invalid explicit origin")
    require(parsed.scheme == "https" or parsed.hostname in ("127.0.0.1", "localhost", "::1"), "HTTP is restricted to loopback")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    folder = args.output / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    report = {"schema": "openstream-results-editor-http-v1", "origin": origin,
              "started_at": datetime.now(timezone.utc).isoformat(), "passed": False,
              "scope": "Every CSV scalar and exposed saved vector; no new solver execution, MATLAB equivalence or experimental validation claim.",
              "cases": [], "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    client = None
    try:
        if parsed.scheme == "https":
            from verify_hosted_gui import HTTPClient
            password = os.environ.pop("OPENSTREAM_VERIFY_PASSWORD", None) or getpass.getpass("OpenSTREAM password: ")
            client = HTTPClient(origin, password, timeout=120)
            code, _, _ = client.request("GET", f"/api/runs/{CASES[0][1]}/export/inputs.csv")
            require(code == 401, "CSV endpoint permitted anonymous access")
            report["anonymous_csv_http_status"] = code
            code, session, _ = client.json("GET", "/auth/session")
            require(code == 200, "Authentication bootstrap failed")
            client.set_csrf(session["csrf"])
            code, session, _ = client.json("POST", "/auth/login", {"password": password})
            require(code == 200 and session["authenticated"], "Authentication failed")
            client.set_csrf(session["csrf"])
        else:
            client = LocalReader(origin)
        unit_metadata = json.loads((ROOT / "src/openstream/data/gui_fields.json").read_text(encoding="utf-8"))["fields"]
        for number, (framework, run_id) in enumerate(CASES, 1):
            reference = args.reference_root / f"{number:02d}-{framework}"
            payload = json.loads((reference / "submitted_inputs.json").read_text(encoding="utf-8"))
            datasets = load_arrays(reference / "extracted/output")
            case = {"framework": framework, "run_id": run_id, "csv": {}}
            report["cases"].append(case)
            for kind in KINDS:
                code, body, _ = client.request("GET", f"/api/runs/{run_id}/export/{kind}.csv")
                require(code == 200, f"{framework}/{kind}: HTTP {code}")
                checked = (check_results_csv(body, datasets) if kind == "results"
                           else {"elements": check_input_csv(body, kind, payload, unit_metadata)})
                case["csv"][kind] = {"passed": True, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), **checked}
                if args.save_csv:
                    (folder / f"{framework}-{kind}.csv").write_bytes(body)
            code, body, _ = client.request("GET", f"/api/runs/{run_id}/data")
            require(code == 200, f"{framework}/plot-data: HTTP {code}")
            case["plot_data"] = {"passed": True, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), **check_plot_data(body, datasets)}
            print(f"{framework}: four CSV exports and all saved vectors passed.", flush=True)
        report["passed"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if parsed.scheme == "https" and client is not None and client.csrf:
            try:
                code, _, _ = client.json("POST", "/auth/logout", {})
                report["logout_http_status"] = code
                require(code == 200, "Logout failed")
            except Exception:
                report["passed"] = False
                report["logout_error"] = "Logout could not be confirmed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (folder / "receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence: {folder}", flush=True)
    print("Results editor verification passed." if report["passed"] else "Results editor verification failed; see receipt.", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
