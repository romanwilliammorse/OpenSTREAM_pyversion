"""Verify the isolated FourField precursor-selection patch without solving.

Transform the recorded pre-change AST only at the two call arguments, required
keyword parameter and local precursor assignment. Require the whole resulting
module AST to match the current file, and all other native modules to match the
specified commit after line-ending normalization. Never overwrite a receipt.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
TARGET = "src/openstream/fourfield.py"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_bytes(commit, path):
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT,
                          check=True, capture_output=True).stdout


def canonical(tree):
    return ast.dump(tree, annotate_fields=True, include_attributes=False)


def check_patch(before, after):
    expected = ast.parse(before)
    original = deepcopy(expected)
    cls = next(n for n in expected.body if isinstance(n, ast.ClassDef) and n.name == "FourFieldSolver")
    solve = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "solve")
    advance = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_advance")
    calls = sorted((n for n in ast.walk(solve) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == "_advance"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"),
                   key=lambda n: n.lineno)
    if len(calls) != 2 or any(c.keywords for c in calls):
        raise ValueError("Expected exactly two original positional _advance calls")
    expected_first_args = ("self.filmInit[k - 1]", "self.film[k - 1]")
    for call, first_arg, selection in zip(calls, expected_first_args,
                                         ("self.mixSolver.mixture[0]", "self.mixSolver.mixture[k]")):
        if len(call.args) != 4 or ast.unparse(call.args[0]) != first_arg:
            raise ValueError("Unexpected initialization/transient call structure")
        call.keywords.append(ast.keyword(arg="sweep_mix", value=ast.parse(selection, mode="eval").body))
    if advance.args.kwonlyargs or advance.args.kw_defaults:
        raise ValueError("Original _advance unexpectedly has keyword-only parameters")
    advance.args.kwonlyargs.append(ast.arg(arg="sweep_mix"))
    advance.args.kw_defaults.append(None)  # required, no implicit fallback
    assignments = [n for n in ast.walk(advance) if isinstance(n, ast.Assign)
                   and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                   and n.targets[0].id == "mix"]
    if len(assignments) != 1 or ast.unparse(assignments[0].value) != "film.mix":
        raise ValueError("Expected one original local mix = film.mix assignment")
    assignments[0].value = ast.Name(id="sweep_mix", ctx=ast.Load())
    actual = ast.parse(after)
    if canonical(expected) != canonical(actual):
        raise ValueError("Current FourField differs beyond the four permitted AST edits")
    return {"permitted_ast_edits": [
                "Initialization call: sweep_mix=self.mixSolver.mixture[0]",
                "Transient call: sweep_mix=self.mixSolver.mixture[k]",
                "Required keyword-only _advance parameter: sweep_mix",
                "Local precursor assignment: mix=sweep_mix"],
            "whole_module_matches_only_permitted_edits": True,
            "before_ast_sha256": digest(canonical(original).encode()),
            "after_ast_sha256": digest(canonical(actual).encode())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    before = git_bytes(args.before_commit, TARGET)
    after = (ROOT/TARGET).read_bytes()
    result = check_patch(before.decode("utf-8"), after.decode("utf-8"))
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", args.before_commit, "src/openstream"],
                           cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    other_modules = {}
    for name in files:
        if name == TARGET or not name.endswith(".py"):
            continue
        old = git_bytes(args.before_commit, name).replace(b"\r\n", b"\n")
        current = (ROOT/name).read_bytes().replace(b"\r\n", b"\n")
        if old != current:
            raise ValueError(f"Unexpected additional native module change: {name}")
        other_modules[name] = digest(current)
    result.update({
        "schema": "openstream-fourfield-precursor-patch-audit-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Source AST and exact normalized-byte scope verification only; no solver or equivalence claim.",
        "before_commit": args.before_commit, "source_path": TARGET,
        "before_git_blob_sha256": digest(before), "after_file_sha256": digest(after),
        "other_native_modules_unchanged_sha256_lf": other_modules,
        "audit_script_sha256": digest(Path(__file__).read_bytes()),
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "sha256": digest(args.output.read_bytes()),
                      "unchanged_native_modules": len(other_modules)}))


if __name__ == "__main__":
    main()
