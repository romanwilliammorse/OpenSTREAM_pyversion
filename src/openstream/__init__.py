"""Native Python port of OpenSTREAM. Coverage is documented in FEATURE_MAP.md."""
from .inputs import InputSet, Model, Options, Geometry, BoundaryConditions
from .properties import FluidProperties
from .solver import MixtureSolver, SolverState
from .twofluid import TwoFluidSolver
from .threefield import ThreeFieldSolver
from .fourfield import FourFieldSolver
from .plotting import SavedResults

__version__ = "0.2.1"


