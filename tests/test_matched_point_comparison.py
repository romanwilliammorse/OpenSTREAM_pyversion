import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("cmp",ROOT/"tools/compare_matched_point_traces.py")
cmp=importlib.util.module_from_spec(spec); spec.loader.exec_module(cmp)


class PointComparisonTest(unittest.TestCase):
    def make(self,p,rows):
        p.write_text("time_s,node_zero_based,iteration,node_one_based,liquid_W\n"+"\n".join(rows)+"\n")

    def test_strict_join_missing_rows_and_first_numeric_difference(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/"a.csv",Path(d)/"b.csv"
            self.make(a,["1,397,1,398,0.01","1,397,2,398,0.02"])
            self.make(b,["1,397,1,398,0.011","1,397,3,398,0.02"])
            r=cmp.compare_tables(a,b,["liquid_W"])
            self.assertEqual(r["matched_rows"],1)
            self.assertEqual(r["missing_from_matlab"],[[1.,397.,2.]])
            self.assertEqual(r["missing_from_native"],[[1.,397.,3.]])
            self.assertAlmostEqual(r["first_difference"]["absolute_difference"],.001)

    def test_duplicate_shape_nonfinite_key_and_wrong_index_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.csv"
            for rows in [["1,1,1,2,.1","1,1,1,2,.2"],["NaN,1,1,2,.1"],["1,1,1,3,.1"],["1,1,1,2"]]:
                self.make(p,rows)
                with self.assertRaises(ValueError): cmp.read_trace(p)

    def test_nonfinite_and_zero_reference_reported_without_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/"a.csv",Path(d)/"b.csv"
            self.make(a,["1,1,1,2,NaN","1,1,2,2,.001"])
            self.make(b,["1,1,1,2,NaN","1,1,2,2,0"])
            r=cmp.compare_tables(a,b,["liquid_W","missing_quantity"])
            self.assertEqual(r["columns"]["liquid_W"]["nonfinite_count"],1)
            self.assertEqual(r["first_difference"]["kind"],"nonfinite_same")
            self.assertEqual(r["missing_columns"]["matlab"],["missing_quantity"])
            self.assertNotIn("passed",r)


if __name__=="__main__": unittest.main()
