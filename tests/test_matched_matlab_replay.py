"""Static scientific safeguards for the external MATLAB replay kit (no runtime claim)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_matched_matlab_replay", ROOT / "tools/prepare_matched_matlab_replay.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class MatchedMatlabKitTest(unittest.TestCase):
    def test_input_numbers_roundtrip_and_column_major(self):
        value = {"A": [[1.2566e-5, 1e-14], [507550.5738, -3.141592653589793]], "KTRELAX": ["NaN"]}
        text = kit.inp_text(value)
        nums = [float(x) for x in text.splitlines()[0].split(">")[1].split()]
        np.testing.assert_array_equal(nums, np.asarray(value["A"]).ravel(order="F"))
        self.assertIn("> NaN", text)

    def test_frozen_input_roundtrip(self):
        from openstream.inputs import read_input_file
        frozen = json.loads((ROOT / "examples/matched_diagnostic_replay.json").read_text())
        for case in frozen["cases"]:
            inputs = json.loads((ROOT / case["original_directory"] / "effective_inputs.json").read_text())
            for group in [inputs["model"], inputs["options"], inputs["geometry"], inputs["bc"][0]]:
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / "input.inp"
                    serial = kit.inp_text(group)
                    # Native Python intentionally refuses MATLAB function handles;
                    # check that literal separately and parse all remaining fields.
                    if "CBTMULT" in group:
                        self.assertIn("CBTMULT ! frozen effective input > @(z) 1", serial)
                        serial = "\n".join(line for line in serial.splitlines() if not line.startswith("CBTMULT "))
                    p.write_text(serial)
                    parsed = read_input_file(p)[0]
                for key, expected in group.items():
                    if key == "CBTMULT":
                        continue
                    elif isinstance(expected, str):
                        self.assertEqual(parsed[key], expected)
                    else:
                        e = np.asarray(kit.flatten(expected), dtype=float)
                        np.testing.assert_array_equal(np.asarray(parsed[key], dtype=float).ravel(), e, err_msg=key)

    def test_hooks_remove_to_exact_original_and_gate_is_preserved(self):
        for fw, nodes in [("FourField", list(range(20,29))), ("TwoFluid", list(range(397,401)))]:
            rel = f"+Solvers/+{fw}/@{fw}Solver/solve.m"
            data = kit.git(ROOT / "upstream", "show", "HEAD:"+rel)
            patched, info = kit.instrument(data, fw, nodes)
            restored = patched.decode()
            for hook in info["hooks"]:
                restored = restored.replace(hook["inserted_text"], "", 1)
                self.assertIn(hook["anchor"], patched.decode())
            self.assertEqual(restored.encode(), data)
            self.assertIn("node_zero_based", info["point_columns"])
            self.assertEqual(info["units"]["time_s"], "s")
        _, temporal, units = kit.trace_spec("FourField")
        self.assertNotIn("timeDFw", temporal["all_temporal_criteria_pass"])
        self.assertEqual(temporal["active_time_dFw"], "false")
        self.assertEqual(units["dWLb"], "kg/s/m")

    def test_changed_source_and_overwrite_are_rejected(self):
        with self.assertRaises(ValueError):
            kit.instrument(b"different source", "FourField", [20])
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError):
                kit.prepare(Path(d))


if __name__ == "__main__":
    unittest.main()
