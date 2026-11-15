# Start OpenSTREAM on this computer

Double-click **OpenSTREAM GUI** on the Desktop for the graphical interface.
Choose a framework, inspect the reference/default inputs, and click **Check**,
then **Run**. Use **Results → Quantity** for interactive plots and **Save PNG**
to export the chart. **Import** and **Export** load/save input JSON; **Cancel**
stops a running calculation. Full instructions: [GUI.md](GUI.md).

## Python console

Double-click **OpenSTREAM Python** on the Desktop, or `OpenSTREAM.cmd` in the
project folder. This opens Python's IDLE command window with OpenSTREAM loaded.
The console is an alternative to the GUI; no MATLAB or Octave is involved.

At the `>>>` prompt, enter a command below and press Enter. Do not include `>>>`
when copying. Wait for the next prompt before entering another command.

| Command | What it does |
|---|---|
| `sample()` | Run the official steady mixture calculation and open its six-panel plot |
| `checks()` | Run quick input, property, mixture and plotting checks |
| `checks(full=True)` | Run the package's native/GUI pytest suite |
| `transient()` | Run the original TUTORIAL2A 0–5 s power-reduction case |
| `plot("H", kind="history")` | Plot outlet enthalpy versus physical time |
| `plot("H", kind="map")` | Plot enthalpy versus position and physical time |
| `animate("H")` | Save and open an animated axial enthalpy profile |
| `plot("VF")` | Plot void fraction along the channel |
| `sample(power_W=70000, cells=100)` | Change the steady power to 70 kW |
| `quantities()` | List available names and units |
| `results()` | Open the latest calculation's output folder |
| `guide()` | Show the in-window help |

`H` is specific enthalpy [J/kg], `P` pressure [Pa], `U` velocity [m/s], `W`
mass flow [kg/s], `T` temperature [K], and `VF` void fraction [dimensionless].
For wall heat flux use `plot("HFLUX", wall=0)`; wall indices start at zero.

Each run or plot creates a unique directory under `outputs/interactive`.
Existing calculations and references are never overwritten. The variable
`solver` retains the latest solved MixtureSolver for direct Python inspection.

Before your first new transient, history/map/animation commands read the
already computed original mixture transient. They print the source directory
explicitly. After `transient()`, they use the new calculation. A steady result
contains only one physical time and cannot supply a physical-time history.
Use `plot("H", kind="history", phase="initialization")` for a separately
labelled pseudo-time convergence history. GIF playback speed is for viewing;
the timestamp on each frame is the saved simulation time.

Closing a plot does not close the command window. Close the IDLE window to exit.
You can instead use the original PowerShell CLI described in README.md.

These are Python commands, not natural-language prompts. In Codex you can ask:

- “Run the official OpenSTREAM mixture sample and show its plots.”
- “Run the quick OpenSTREAM checks and explain any failures.”
- “Run the power-reduction transient and show outlet enthalpy and void fraction over time.”
- “Compare the mixture sample at 50, 100 and 200 cells; plot pressure drop and report convergence.”

All four original steady baselines agree with their archived MATLAB core
profiles. Full feature parity and transient equivalence remain unfinished.
The two-fluid, three-field and four-field examples retain known physical
consistency failures. Experimental validation against
[OpenSTREAM-database](https://github.com/OpenSTREAM-solvers/openstream-database)
has not yet been executed. Read [PARITY_STATUS.md](PARITY_STATUS.md) before
interpreting predictions.

