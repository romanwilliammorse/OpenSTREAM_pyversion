"""Native Python port of OpenSTREAM. Coverage is documented in FEATURE_MAP.md.

Public classes are loaded on first access. Importing the package for hosted
input validation or saved-result delivery does not load the scientific solver
environment; requesting a solver still imports the original implementation.
"""
from importlib import import_module as _import_module

__version__ = "0.2.1"

_EXPORTS = {
    "InputSet": ".inputs",
    "Model": ".inputs",
    "Options": ".inputs",
    "Geometry": ".inputs",
    "BoundaryConditions": ".inputs",
    "FluidProperties": ".properties",
    "MixtureSolver": ".solver",
    "SolverState": ".solver",
    "TwoFluidSolver": ".twofluid",
    "ThreeFieldSolver": ".threefield",
    "FourFieldSolver": ".fourfield",
    "SavedResults": ".plotting",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_import_module(module, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


