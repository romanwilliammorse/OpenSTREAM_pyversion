"""Static, inheritance-aware upstream/native API inventory (standard library only).

This is a reproducible name and declaration audit, never proof of mathematical
equivalence, branch completeness, correctness, or physical validity. No solver
or CoolProp import occurs. The MATLAB reader is deliberately limited to this
pinned repository's class formatting; private/protected helpers are excluded.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


CLASS_MAP = {
    "Inputs.Input":"inputs._Input", "Inputs.Model":"inputs.Model", "Inputs.Options":"inputs.Options",
    "Inputs.Geometry":"inputs.Geometry", "Inputs.BoundaryConditions":"inputs.BoundaryConditions",
    "Inputs.InputSet":"inputs.InputSet", "Inputs.FluidProperties":"properties.FluidProperties",
    "Solvers.AbstractField":"annular.AnnularField", "Solvers.AbstractFilm":"annular.Film",
    "Solvers.Mixture.Mixture":"fields.Mixture", "Solvers.Mixture.Liquid":"fields.Liquid",
    "Solvers.Mixture.Vapor":"fields.Vapor", "Solvers.TwoFluid.Mixture":"tf_fields.TwoFluidMixture",
    "Solvers.TwoFluid.Liquid":"tf_fields.Liquid", "Solvers.TwoFluid.Vapor":"tf_fields.Vapor",
    "Solvers.ThreeField.Film":"annular.Film", "Solvers.ThreeField.Drop":"annular.Drop",
    "Solvers.FourField.Film":"ff_fields.Film", "Solvers.FourField.Base":"ff_fields.Base",
    "Solvers.FourField.Wave":"ff_fields.Wave", "Solvers.FourField.Drop":"annular.Drop",
    "Solvers.Mixture.MixtureSolver":"solver.MixtureSolver", "Solvers.TwoFluid.TwoFluidSolver":"twofluid.TwoFluidSolver",
    "Solvers.ThreeField.ThreeFieldSolver":"threefield.ThreeFieldSolver", "Solvers.FourField.FourFieldSolver":"fourfield.FourFieldSolver",
}
ALIASES = {"initializeSolver":"initialize_solver", "copyFlowProperties":"copy_flow_properties",
           "initializeBaseAndWave":"initialize_base_wave", "interpBoundaryConditions":"_interpolate_boundary_conditions",
           "applySolverDependentProps":"for_solver"}
INFRASTRUCTURE = {"log", "warning", "solverName", "memoizeFunction", "CreateITR", "getStruct", "struct", "save",
                  "transient", "plot", "plotz", "plott", "plotzt", "writeInputFile", "convert2JSON",
                  "validateFunctionHandleInput", "validateInputEntry", "getProperties", "listInputProperties", "defaultValueUsedReport"}
ALTERNATIVES = {
    "transient":"SavedResults preserves saved arrays/slicing only; no generic live-object method or recomputation of unsaved closures.",
    "plott":"SavedResults.history for saved quantities; documented plotting subset, not a signature-compatible alias.",
    "plotzt":"SavedResults.space_time for saved quantities; documented plotting subset.",
    "plotz":"SavedResults.axial and output plotting; plotting option parity is incomplete.",
    "timeInterpolate":"numerics.interpolate and solver boundary interpolation implement the operation internally; public wrapper absent.",
    "axialInterpolate":"numerics.interpolate and solver boundary interpolation implement the operation internally; public wrapper absent.",
    "CreateITR":"Iteration arrays are initialized directly in native constructors; no shared public factory.",
    "getStruct":"Portable save methods and input to_dict replace MATLAB-object serialization in part.",
    "struct":"Portable save methods and input to_dict replace MATLAB-object serialization in part; no generic live field struct method.",
    "applySolverDependentProperties":"Model.for_solver resolves source solver-dependent defaults; generic Input wrapper is absent.",
}
REVIEWED = {
    "Solvers.Mixture.Mixture.MTRANSV": {
        "kind":"unused_closure_review", "units":"kg/(s m)",
        "note":"Transverse wall-region vapor exchange with fixed 0.01 s relaxation. Source says currently not used and is not included in MTOT/HTOT. Porting its diagnostic must not silently add new governing physics."},
    "Solvers.Mixture.Mixture.KLOCZ": {
        "kind":"mesh_location_diagnostic_review", "units":"m",
        "note":"Returns actual mesh-node obstruction locations through KIDX(zIdx), not merely input KLOC. Native API was added after initial inventory, with subset/duplicate/tie tests."},
    "Solvers.Mixture.Mixture.KIDX": {
        "kind":"subset_signature_review", "units":"index",
        "note":"Upstream accepts optional zIdx and filters obstruction indices to that subset. This capability was initially absent; native KIDX(i=None) was added with subset tests."},
    "Solvers.ThreeField.Drop.RE": {
        "kind":"source_defect_requires_explicit_error", "units":"1",
        "note":"Upstream expression calls drop.MU(zIdx), absent from Drop and AbstractField. Do not substitute vapor-relative REV, which is a different Reynolds number. FourField.Drop inherits this gap."},
    "Solvers.TwoFluid.Vapor.XTR_CBT": {
        "kind":"source_defect_requires_explicit_error", "units":"1",
        "note":"Upstream calls liquid.XTR_CBT(), which is not defined by Liquid or its ancestors. Needs explicit defect policy rather than invented transition quality."},
    "Inputs.FluidProperties.transient": {
        "kind":"property_series_api_review",
        "note":"Upstream gathers time-indexed fluid-property scalars. This API was initially missing; inspect the native candidate and tests for current implementation, not just scalar property availability."},
}
for method, units in (("TSAT","K"),("HF","J/kg"),("HG","J/kg")):
    REVIEWED[f"Inputs.BoundaryConditions.{method}"] = {
        "kind":"pressure_dependent_boundary_diagnostic", "units":units,
        "note":"Source queries the supplied wrapper at boundary.PRESSURE, which need not equal supplied FluidProperties.PRESSURE. A constant accessor alone is not equivalent; native API must query BC pressure or explicitly check pressure agreement."}
for phase in ("Liquid", "Vapor"):
    for method in ("TIME", "Z"):
        REVIEWED[f"Solvers.Mixture.{phase}.{method}"] = {
            "kind":"phase_coordinate_api_review", "units":"s" if method == "TIME" else "m",
            "note":"Upstream delegates to parent mixture coordinates. Native public phase methods were added after initial inventory; tests check subset shape, current time and no mutable mesh alias."}
for method in ("XTR_SUB", "XTR_SAT", "XTR_ITM", "XTR_ANN"):
    REVIEWED[f"Solvers.TwoFluid.Vapor.{method}"] = {
        "kind":"forwarding_diagnostic_review", "units":"1",
        "note":f"Upstream delegates to liquid.{method}(). Vapor forwarding methods were added after initial inventory and checked against the native Liquid values."}


def sha(path):
    # Text-only declaration provenance must survive Git's Windows newline conversion.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def matlab_classes(root):
    classes = {}
    files = list((root/"upstream/+Solvers").rglob("*.m"))+list((root/"upstream/+Inputs").glob("*.m"))
    for path in files:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        header = next((x for x in lines if x.startswith("classdef")), None)
        if header is None:
            continue
        match = re.match(r"classdef\s+(?:\([^)]*\)\s*)?(\w+)(?:\s*<\s*(.*))?", header)
        name = ".".join([part[1:] for part in path.relative_to(root/"upstream").parts[:-1] if part.startswith("+")]+[match[1]])
        info = {"file":str(path.relative_to(root)).replace("\\", "/"), "sha256":sha(path),
                "bases":re.findall(r"[\w.]+", (match[2] or "").split("%")[0]), "methods":{}}
        access, abstract = None, False
        for number, line in enumerate(lines, 1):
            if re.match(r"^    methods\b", line):
                access = "restricted" if re.search(r"Access\s*=\s*(private|protected|\{)", line) else "public"
                abstract = bool(re.search(r"\bAbstract\b", line))
            elif re.match(r"^    end\s*(%.*)?$", line):
                access, abstract = None, False
            if access != "public":
                continue
            if re.match(r"^        function\b", line):
                declaration = line.strip().split("%", 1)[0]
                k = number
                while declaration.rstrip().endswith("..."):
                    declaration = declaration.rstrip()[:-3]+" "+lines[k].strip().split("%",1)[0]
                    k += 1
                head = declaration[len("function"):].strip().split("(", 1)[0]
                method = head.split("=")[-1].strip()
                info["methods"][method] = {"name":method, "line":number, "declaration":declaration,
                                             "declaring_class":name, "file":info["file"], "abstract":False}
            elif abstract and re.match(r"^        [A-Za-z]\w*\s*$", line):
                method = line.strip()
                info["methods"][method] = {"name":method, "line":number, "declaration":method,
                                             "declaring_class":name, "file":info["file"], "abstract":True}
        external = path.parent/"solve.m"
        if path.parent.name.startswith("@") and external.exists():
            info["methods"]["solve"] = {"name":"solve", "line":1, "declaration":external.read_text().splitlines()[0],
                                           "declaring_class":name, "file":str(external.relative_to(root)).replace("\\", "/"), "abstract":False}
        classes[name] = info
    return classes


def python_classes(root):
    classes = {}
    for path in (root/"src/openstream").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        imports = {alias.asname or alias.name:f"{node.module}.{alias.name}" for node in tree.body
                   if isinstance(node, ast.ImportFrom) and node.level == 1 for alias in node.names}
        module = path.stem
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            name = module+"."+node.name
            bases = [imports.get(ast.unparse(base),module+"."+ast.unparse(base)) for base in node.bases]
            methods = {}
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = [x for x in method.body if not (isinstance(x,ast.Expr) and isinstance(x.value,ast.Constant) and isinstance(x.value.value,str))]
                    always_unsupported = bool(body and isinstance(body[0],ast.Raise) and isinstance(body[0].exc,ast.Call)
                        and isinstance(body[0].exc.func,ast.Name) and body[0].exc.func.id=="NotImplementedError")
                    methods[method.name] = {"name":method.name, "declaring_class":name,
                        "file":str(path.relative_to(root)).replace("\\", "/"), "line":method.lineno,
                        "signature":ast.unparse(method.args), "property":any(ast.unparse(d)=="property" for d in method.decorator_list),
                        "unconditional_NotImplementedError":always_unsupported,
                        "contains_NotImplementedError":any(isinstance(x,ast.Raise) and isinstance(x.exc,ast.Call)
                            and isinstance(x.exc.func,ast.Name) and x.exc.func.id=="NotImplementedError" for x in ast.walk(method))}
            classes[name] = {"file":str(path.relative_to(root)).replace("\\", "/"), "sha256":sha(path), "bases":bases, "methods":methods}
    return classes


def inherited(classes, name, visited=None):
    visited = set() if visited is None else visited
    if name not in classes or name in visited:
        return {}
    visited.add(name)
    result = {}
    for base in reversed(classes[name]["bases"]):
        result.update(inherited(classes, base, visited.copy()))
    result.update(classes[name]["methods"])
    return result


def build_report(root):
    upstream, native = matlab_classes(root), python_classes(root)
    feature_path = root/"docs/FEATURE_MAP.md"
    feature = feature_path.read_text(encoding="utf-8")
    records, summary = [], {}
    for source_class, target_class in CLASS_MAP.items():
        target_methods = inherited(native, target_class)
        rows = []
        for name, source in sorted(inherited(upstream, source_class).items()):
            identity = source["declaring_class"]+"."+name
            target_name = ALIASES.get(name, name)
            if name.startswith("get."):
                target_name = name[4:]
            candidate = target_methods.get(target_name)
            if name == source["declaring_class"].split(".")[-1]:
                status = "constructor_outside_numerical_method_count"
            elif name.startswith("set."):
                status = "property_assignment_contract_needs_review"
            elif candidate and candidate["unconditional_NotImplementedError"]:
                status = "native_explicit_unsupported_method"
            elif candidate:
                status = "native_name_candidate_not_correctness_proof"
            elif name in ALTERNATIVES:
                status = "partial_or_internal_alternative"
            elif name in INFRASTRUCTURE:
                status = "infrastructure_or_presentation_gap"
            else:
                status = "unmapped_public_method"
            row = {"upstream_class":source_class, "native_class":target_class,
                   "source":source, "status":status, "native_candidate":candidate,
                   "explicit_token_in_feature_map":bool(re.search(r"(?<!\w)"+re.escape(name)+r"(?!\w)", feature))}
            if name in ALTERNATIVES and candidate is None:
                row["alternative_note"] = ALTERNATIVES[name]
            if identity in REVIEWED:
                row["independent_review"] = REVIEWED[identity]
            rows.append(row)
        records.extend(rows)
        summary[source_class] = dict(Counter(row["status"] for row in rows))
    reviewed = [r for r in records if "independent_review" in r]
    source_files = {x["file"]:x["sha256"] for x in upstream.values()}
    source_files.update({r["source"]["file"]:sha(root/r["source"]["file"]) for r in records})
    return {"schema":"openstream-method-audit-v1",
        "fingerprint_policy":"SHA256 of source-text bytes with CRLF normalized to LF; no other normalization.",
        "scope":"Public methods in pinned solver/field classes and Inputs classes listed in class_mapping, including inherited methods.",
        "limitations":["Static declaration/name audit only; no execution, equation validation, branch coverage, or numerical-equivalence proof.",
                       "MATLAB parser relies on this repository's four-space class-section/eight-space method formatting; nested functions and private/protected methods are excluded.",
                       "Python inheritance is resolved from AST and local imports; dynamically generated methods/attributes are not inferred.",
                       "Name candidates can have incomplete argument coverage; explicit unsupported flags only inspect local raise statements.",
                       "Feature-map token search is literal evidence, not proof that a broader prose capability includes or excludes a method.",
                       "General CoolPropWrapper humid-air/unit-conversion utilities, logging/session UI, tutorials, MATLAB built-in inherited APIs and SolverPlotter style parity are outside this numerical-method inventory."],
        "class_mapping":CLASS_MAP, "feature_map_sha256":sha(feature_path),
        "upstream_files":source_files,
        "native_files":{x["file"]:x["sha256"] for x in native.values()},
        "summary_counts_not_coverage_scores":summary,
        "reviewed_findings_including_resolved_gaps":reviewed, "methods":records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("docs/METHOD_COVERAGE.json"))
    args = parser.parse_args()
    report = build_report(args.root)
    path = args.output if args.output.is_absolute() else args.root/args.output
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(path)
    print(json.dumps(dict(Counter(r["status"] for r in report["methods"])),indent=2))
    seen = set()
    for row in report["methods"]:
        identity = row["source"]["declaring_class"]+"."+row["source"]["name"]
        if row["status"] == "unmapped_public_method" and identity not in seen:
            seen.add(identity)
            print("UNMAPPED",identity)


if __name__ == "__main__":
    main()
