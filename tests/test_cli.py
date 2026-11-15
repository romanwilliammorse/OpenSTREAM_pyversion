"""Exercise CLI dispatch and framework-independent progress/error reporting."""
from types import SimpleNamespace
import pytest
from openstream import cli


@pytest.mark.parametrize("framework", ["mixture", "twofluid", "threefield", "fourfield"])
def test_default_progress_supports_each_framework(monkeypatch, tmp_path, capsys, framework):
    # Framework-specific convergence columns differ. Only common columns are
    # required for progress; complete increment histories are saved to CSV.
    class Solver:
        def __init__(self, inputs):
            self.STATE = SimpleNamespace(name="SOLVEDCONVERGED")
            self.converged = True
            self.mixSolver = self
        def solve(self, progress):
            progress(dict(phase="initialization", time_s=1., max_iterations=3, point_converged=True))
            return self
        def save(self, output):
            output.mkdir()
    names = {"mixture": "MixtureSolver", "twofluid": "TwoFluidSolver",
             "threefield": "ThreeFieldSolver", "fourfield": "FourFieldSolver"}
    monkeypatch.setattr(cli if framework == "mixture" else __import__("openstream"), names[framework], Solver)
    monkeypatch.setattr(cli, "balances", lambda solver: {})
    result = cli.main(["sample", "--framework", framework, "--output", str(tmp_path/"run")])
    assert result == 0
    assert "point_converged=True" in capsys.readouterr().out


def test_existing_output_rejected_without_modification(tmp_path):
    (tmp_path/"evidence.txt").write_text("keep me")
    with pytest.raises(SystemExit) as exc:
        cli.main(["sample", "--output", str(tmp_path)])
    assert exc.value.code == 2
    assert (tmp_path/"evidence.txt").read_text() == "keep me"


@pytest.mark.parametrize("converged,physical,expected", [(False, None, 2), (True, False, 3)])
def test_cli_reports_failed_numerics_or_physical_check(monkeypatch, tmp_path, converged, physical, expected):
    class Solver:
        def __init__(self, inputs):
            self.STATE = SimpleNamespace(name="SOLVEDCONVERGED" if converged else "SOLVEDNOTCONVERGED")
            self.converged = converged
            self.mixSolver = self
        def solve(self, progress): return self
        def save(self, output): output.mkdir()
        def diagnostics(self): return {"physical_consistency": physical}
    monkeypatch.setattr(__import__("openstream"), "TwoFluidSolver", Solver)
    monkeypatch.setattr(cli, "balances", lambda solver: {})
    assert cli.main(["sample", "--framework", "twofluid", "--quiet", "--output", str(tmp_path/"run")]) == expected
    assert (tmp_path/"run").is_dir()
