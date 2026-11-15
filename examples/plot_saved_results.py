"""Render saved native results only: no solving and no property calculations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt

from openstream.plotting import SavedResults


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mixture", type=Path, default=root/"outputs/verification/native-sensitivity-01/transient-0.1")
    parser.add_argument("--fourfield", type=Path, default=root/"outputs/fourfield_official")
    parser.add_argument("--output", type=Path, default=root/"outputs/saved-result-plots")
    args = parser.parse_args()
    mixture = SavedResults(args.mixture)
    fourfield = SavedResults(args.fourfield)
    initialization = SavedResults(args.fourfield, phase="initialization")
    args.output.mkdir(parents=True, exist_ok=False)
    figures = {
        "mixture_enthalpy_history.png": mixture.history("H", nodes=[len(mixture.z)//2, len(mixture.z)-1]),
        "mixture_enthalpy_space_time.png": mixture.space_time("H"),
        "fourfield_frequency_axial.png": fourfield.axial("film.wave.FREQUENCY", walls=0),
        "fourfield_frequency_initialization.png": initialization.history("film.wave.FREQUENCY", nodes=[len(initialization.z)//2, len(initialization.z)-1], walls=0),
        "fourfield_wave_mass_space_time.png": initialization.space_time("film.wave.W", wall=0),
    }
    for name, figure in figures.items():
        figure.savefig(args.output/name, dpi=160)
        plt.close(figure)
    mixture.save_animation("H", args.output/"mixture_enthalpy.gif", times=slice(None,None,2), fps=8)
    initialization.save_animation("film.wave.FREQUENCY", args.output/"fourfield_frequency_initialization.gif", walls=0, fps=4)
    sources = [args.mixture/"results.npz", args.mixture/"metadata.json",
               args.fourfield/"results.npz", args.fourfield/"initialization.npz", args.fourfield/"metadata.json"]
    provenance = {"purpose":"Native saved-data rendering; no solver execution or numerical-equivalence claim",
                  "physical_time_source":str(args.mixture.resolve()),
                  "fourfield_source":str(args.fourfield.resolve()),
                  "source_sha256":{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                  "generated":sorted(p.name for p in args.output.iterdir())}
    (args.output/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n",encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
