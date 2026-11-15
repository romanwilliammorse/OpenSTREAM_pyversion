"""Synthetic comparator tests, never MATLAB or physical validation.

Fixtures are created only in TemporaryDirectory and labeled synthetic-test.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from compare_matlab_reference import FRAMEWORKS, POINT_ERRORS, UPSTREAM_COMMIT, WRAPPER_COMMIT, compare, field_path


class SyntheticFixture:
    def __init__(self, directory, framework="Mixture", walls=1):
        self.reference,self.native=directory/"reference",directory/"native"
        self.reference.mkdir();self.native.mkdir()
        self.arrays,self.metadata,self.native_arrays=[],{},{}
        self.manifest={"schema":"openstream-portable-reference-v1","complete":True,
            "framework":framework,"source_kind":"synthetic-test","arrays":self.arrays,
            "runtime":{"coolprop":"8.0.0"},"text_records":[],"convergence_records":[],
            "upstream":{"git_commit":UPSTREAM_COMMIT,"expected_commit":UPSTREAM_COMMIT,"git_status":"",
                         "expected_wrapper_commit":WRAPPER_COMMIT,"submodules":" "+WRAPPER_COMMIT+" +CoolPropWrapper (heads/main)"}}
        payload=b"SYNTHETIC COMPARATOR FIXTURE. NOT MATLAB OR PHYSICAL DATA.\n"
        self.digest=hashlib.sha256(payload).hexdigest()
        (self.reference/"inputs").mkdir()
        (self.reference/"inputs/fixture.inp").write_bytes(payload)
        self.manifest["input_files"]=[{"name":"fixture.inp","sha256":self.digest}]
        self.make_framework("solver",self.native,framework,walls,payload)
        if framework!="Mixture": self.make_framework("solver.mixSolver",self.native/"mixture","Mixture",walls,payload)
        self.flush()

    def add_reference(self,path,values,unit):
        values=np.asarray(values)
        if values.ndim==0: values=values.reshape(1,1)
        elif values.ndim==1: values=values.reshape(-1,1)
        existing=next((item for item in self.arrays if item["path"]==path),None)
        record=existing or {"path":path,"file":f"{len(self.arrays):05d}.csv"}
        record.update(shape=list(values.shape),units=unit)
        if values.size: np.savetxt(self.reference/record["file"],values.reshape(values.shape[0],-1,order="F"),delimiter=",",fmt="%.17g")
        else: (self.reference/record["file"]).write_text("")
        if existing is None: self.arrays.append(record)

    def make_framework(self,prefix,native,framework,walls,payload):
        native.mkdir(exist_ok=True);(native/"inputs").mkdir()
        (native/"inputs/00-fixture.inp").write_bytes(payload)
        options={"MAXITER":100,"ERRORW":.001,"ERRORP":.1,"ERRORH":.1,"ERRORU":.01,
                 "ERRORWF":.0001,"ERRORUF":.01,"ERRORUD":.01,"ERRORFW":.1,
                 "SSCONVW":.001,"SSCONVP":.1,"SSCONVH":.1,"SSCONVU":.01,
                 "SSCONVWF":.0001,"SSCONVUF":.01,"SSCONVUD":.01,"SSCONVFW":.1}
        inputs={"model":{"ID":"SYNTHETIC","NNODES":2,"CBTMULT":"<Python callable>"},
                "options":options,"geometry":{"LENGTH":1,"PERIM":[.2]*walls},"bc":[{"TIME":0}]}
        metadata={"schema":"openstream-python-v1","framework":framework,"upstream_commit":UPSTREAM_COMMIT,
                  "wrapper_commit":WRAPPER_COMMIT,"versions":{"CoolProp":"8.0.0"},"converged":True,
                  "units":{"Z":"m","TIME":"s"},"inputs":inputs,"constants":{"model.G":9.81},
                  "function_samples":{"model.CBTMULT":[1,1,1]},
                  "source_files":[{"source":"fixture.inp","copy":"inputs/00-fixture.inp","sha256":self.digest}]}
        self.metadata[prefix]=(native,metadata)
        self.manifest["convergence_records"].append({"path":prefix,"state_code":1,"state":"SOLVEDCONVERGED"})
        self.manifest["text_records"].append({"path":prefix+".inputs.model","values":{"ID":"SYNTHETIC"}})
        for group,values in inputs.items():
            if group=="bc":continue
            for key,value in values.items():
                if not isinstance(value,str):self.add_reference(prefix+".inputs."+group+"."+key,value,"1")
        self.add_reference(prefix+".inputs.bc[0].TIME",0,"s")
        self.add_reference(prefix+".inputs.model.G",9.81,"m/s^2")
        self.add_reference(prefix+".function_samples.model.CBTMULT",[1,1,1],"1")
        z=np.array([0,.5,1]);self.add_reference(prefix+".Z",z,"m")
        self.add_reference(prefix+".TIME",[0,.1],"s")
        for phase,times in (("physical",[0,.1]),("initialization",[0,1,2])):
            arrays={"Z":z,"TIME":np.array(times,dtype=float)}
            for field,native_field,wall in FRAMEWORKS[framework]:
                keys=[("W","kg/s"),("U","m/s"),("H","J/kg")]
                if field=="film.wave":keys.append(("FREQUENCY","Hz"))
                for key,unit in keys:
                    native_key=(native_field+"." if native_field else "")+key
                    values=np.array([[0.,1.,2.]]) if not wall else np.arange(3*walls).reshape(1,3,walls).astype(float)
                    values=np.repeat(values,len(times),axis=0)
                    if phase=="physical":values[1]+=0.25
                    arrays[native_key]=values;metadata["units"][native_key]=unit
                    for i in range(len(times)):self.add_reference(field_path(prefix,field,phase,i)+"."+key,values[i],unit)
            for root in sorted({f.split(".")[0] for f,_,_ in FRAMEWORKS[framework]}):
                for i,t in enumerate(times):self.add_reference(field_path(prefix,root,phase,i)+".TIME",t,"s")
            for field,errors in POINT_ERRORS[framework].items():
                for i in range(len(times)):
                    parent=field_path(prefix,field,phase,i)
                    self.add_reference(parent+".ITR.N",[0,2,2],"1")
                    for key,_,unit in errors:
                        shape=(3,walls) if field.startswith("film") else (3,1)
                        self.add_reference(parent+".ITR."+key,np.zeros(shape),unit)
            if framework=="Mixture":
                for i in range(len(times)):
                    for key,unit in (("P","Pa"),("MRM.WV","kg/s"),("MRM.HV","J/kg")):
                        self.add_reference(field_path(prefix,"mixture",phase,i)+"."+key,np.ones(3),unit)
            self.native_arrays[(prefix,phase)]=(native,arrays)

    def flush(self):
        (self.reference/"manifest.json").write_text(json.dumps(self.manifest))
        for native,metadata in self.metadata.values():(native/"metadata.json").write_text(json.dumps(metadata))
        for (prefix,phase),(native,arrays) in self.native_arrays.items():
            np.savez(native/("initialization.npz" if phase=="initialization" else "results.npz"),**arrays)

    def compare(self,**kwargs):
        self.flush();return compare(self.reference,self.native,**kwargs)


class ReferenceComparatorTest(unittest.TestCase):
    def fixture(self,framework="Mixture",walls=1):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return SyntheticFixture(Path(temp.name),framework,walls)

    def test_all_frameworks_histories_precursors_json(self):
        for fw in FRAMEWORKS:
            with self.subTest(framework=fw):
                f=self.fixture(fw);r=f.compare();self.assertTrue(r["passed"])
                self.assertEqual(len(r["sections"]),1 if fw=="Mixture" else 2)
                self.assertEqual(r["sections"][0]["selected_indices"],{"physical":[0,1],"initialization":[0,1,2]})
                json.dumps(r,allow_nan=False)

    def test_original_physical_zero_scope(self):
        r=self.fixture("FourField").compare(phase="physical",time_index=0)
        self.assertTrue(r["passed"]);self.assertEqual(len(r["sections"][0]["checks"]),13)

    def test_initialization_only(self):
        r=self.fixture("TwoFluid").compare(phase="initialization")
        self.assertTrue(r["passed"]);self.assertEqual(len(r["sections"][0]["checks"]),18)

    def test_reference_zero_exact_all_frameworks(self):
        for fw in FRAMEWORKS:
            with self.subTest(framework=fw):
                f=self.fixture(fw)
                key={"Mixture":"W","TwoFluid":"liquid.W","ThreeField":"film.W","FourField":"film.base.W"}[fw]
                f.native_arrays[("solver","physical")][1][key].flat[0]=1e-30
                self.assertFalse(f.compare()["passed"])

    def test_relative_tolerance_boundary(self):
        f=self.fixture();a=f.native_arrays[("solver","physical")][1]["W"]
        a[0,1]=1+.99e-8;self.assertTrue(f.compare()["passed"])
        a[0,1]=1+1.01e-8;self.assertFalse(f.compare()["passed"])

    def test_missing_base_not_silent_skip(self):
        f=self.fixture("FourField")
        f.arrays[:]=[x for x in f.arrays if x["path"]!="solver.film[0].base.H"]
        self.assertFalse(f.compare()["passed"])

    def test_basefilm_alias_not_substituted(self):
        f=self.fixture("FourField")
        next(x for x in f.arrays if x["path"]=="solver.film[0].base.H")["path"]="solver.film[0].basefilm.H"
        self.assertFalse(f.compare()["passed"])

    def test_frequency_fixed_supplemental_policy(self):
        f=self.fixture("FourField");f.native_arrays[("solver","physical")][1]["film.wave.FREQUENCY"][0,1,0]+=1e-7
        r=f.compare();self.assertFalse(r["passed"])
        c=next(c for c in r["sections"][0]["checks"] if not c["passed"])
        self.assertIn("provisional",c["scope"]);self.assertEqual((c["rtol"],c["atol"]),(1e-8,0))

    def test_precursor_failure_not_hidden(self):
        f=self.fixture("ThreeField");f.native_arrays[("solver.mixSolver","physical")][1]["H"][0,1]+=1
        r=f.compare();self.assertFalse(r["passed"]);self.assertTrue(r["sections"][0]["passed"])

    def test_initial_history_disagreement_detected(self):
        f=self.fixture("TwoFluid");f.native_arrays[("solver","initialization")][1]["vapor.U"][0,1]+=1
        self.assertFalse(f.compare()["passed"]);self.assertTrue(f.compare(phase="physical")["passed"])

    def test_wall_axes_preserved(self):
        for fw in ("ThreeField","FourField"):
            with self.subTest(framework=fw):
                f=self.fixture(fw,walls=2);self.assertTrue(f.compare()["passed"])
                a=f.native_arrays[("solver","physical")][1];a["film.W"]=a["film.W"].transpose(0,2,1)
                self.assertFalse(f.compare()["passed"])

    def test_no_single_wall_squeeze(self):
        f=self.fixture("ThreeField");a=f.native_arrays[("solver","physical")][1];a["film.W"]=a["film.W"][:,:,0]
        self.assertFalse(f.compare()["passed"])

    def test_mesh_and_time_mismatch_rejected(self):
        for phase,key in (("physical","Z"),("initialization","TIME")):
            with self.subTest(key=key):
                f=self.fixture();f.native_arrays[("solver",phase)][1][key][1]+=.1
                with self.assertRaisesRegex(ValueError,key+" differs"):f.compare()

    def test_point_failure_cannot_hide_in_physical_zero(self):
        f=self.fixture("FourField");f.add_reference("solver.filmInit[2].wave.ITR.DF",[0,.2,0],"Hz")
        with self.assertRaisesRegex(ValueError,"point-convergence"):f.compare(phase="physical",time_index=0)

    def test_actual_iteration_count_required(self):
        f=self.fixture("TwoFluid");f.add_reference("solver.liquidInit[2].ITR.N",[0,0,0],"1")
        with self.assertRaisesRegex(ValueError,"actual point-iteration"):f.compare()

    def test_temporal_failure_rejected(self):
        f=self.fixture();f.add_reference("solver.mixtureInit[2].P",[1,2,1],"Pa")
        with self.assertRaisesRegex(ValueError,"temporal criterion"):f.compare()

    def test_frequency_temporal_stop_checked(self):
        f=self.fixture("FourField");f.add_reference("solver.filmInit[2].wave.FREQUENCY",[0,1.2,2],"Hz")
        with self.assertRaisesRegex(ValueError,"SSCONVFW"):f.compare()

    def test_intermediate_pseudo_failure_allowed(self):
        f=self.fixture("ThreeField");f.add_reference("solver.filmInit[1].ITR.DU",[0,9,9],"m/s")
        self.assertTrue(f.compare()["passed"])

    def test_transient_point_failure_rejected(self):
        f=self.fixture("TwoFluid");f.add_reference("solver.vapor[1].ITR.DU",[0,2,0],"m/s")
        with self.assertRaisesRegex(ValueError,"point-convergence"):f.compare()
        self.assertTrue(f.compare(phase="physical",time_index=0)["passed"])

    def test_dfw_does_not_substitute_for_df(self):
        f=self.fixture("FourField")
        next(x for x in f.arrays if x["path"]=="solver.filmInit[2].wave.ITR.DF")["path"]="solver.filmInit[2].wave.ITR.DFW"
        with self.assertRaisesRegex(ValueError,"Missing reference array.*DF"):f.compare()

    def test_nonfinite_and_units_fail(self):
        for mode in ("NaN","units"):
            with self.subTest(mode=mode):
                f=self.fixture("TwoFluid")
                if mode=="NaN":f.native_arrays[("solver","physical")][1]["liquid.H"][0,1]=np.nan
                else:f.metadata["solver"][1]["units"]["liquid.H"]="kJ/kg"
                self.assertFalse(f.compare()["passed"])

    def test_provenance_gates(self):
        for mode,message in (("commit","Source commit"),("input","Effective numeric input"),("version","CoolProp versions"),("function","Effective numeric input")):
            with self.subTest(mode=mode):
                f=self.fixture("FourField");m=f.metadata["solver"][1]
                if mode=="commit":m["upstream_commit"]="c"*40
                elif mode=="input":m["inputs"]["model"]["NNODES"]=3
                elif mode=="version":m["versions"]["CoolProp"]="7.0.0"
                else:m["function_samples"]["model.CBTMULT"]=[1,2,1]
                with self.assertRaisesRegex(ValueError,message):f.compare()

    def test_precursor_provenance_gate(self):
        f=self.fixture("ThreeField");f.metadata["solver.mixSolver"][1]["constants"]["model.G"]=10
        with self.assertRaisesRegex(ValueError,"Gravity constant"):f.compare()

    def test_input_tampering_rejected(self):
        f=self.fixture();(f.native/"inputs/00-fixture.inp").write_text("changed")
        with self.assertRaisesRegex(ValueError,"input hash mismatch"):f.compare()

    def test_legacy_schema_requires_framework(self):
        f=self.fixture("ThreeField");del f.metadata["solver"][1]["schema"]
        self.assertTrue(f.compare()["passed"]);f.metadata["solver"][1]["framework"]="FourField"
        with self.assertRaisesRegex(ValueError,"schema|framework"):f.compare()

    def test_matlab_single_json_struct(self):
        f=self.fixture();f.manifest["convergence_records"]=f.manifest["convergence_records"][0]
        self.assertTrue(f.compare()["passed"])

    def test_empty_input_preserved(self):
        f=self.fixture();f.metadata["solver"][1]["inputs"]["model"]["KLOC"]=[]
        f.add_reference("solver.inputs.model.KLOC",np.empty((0,0)),"m")
        self.assertTrue(f.compare()["passed"])

    def test_csv_shape_and_path_checked(self):
        f=self.fixture();item=next(x for x in f.arrays if x["path"]=="solver.mixture[0].H")
        np.savetxt(f.reference/item["file"],np.array([[0,1,2]]),delimiter=",")
        with self.assertRaisesRegex(ValueError,"CSV dimensions"):f.compare()
        item["file"]="../escape.csv"
        with self.assertRaisesRegex(ValueError,"escapes"):f.compare()

    def test_duplicate_and_noncontiguous_paths_rejected(self):
        f=self.fixture();f.arrays.append(f.arrays[0].copy())
        with self.assertRaisesRegex(ValueError,"Duplicate array paths"):f.compare()
        f.arrays.pop();f.arrays[:]=[x for x in f.arrays if not x["path"].startswith("solver.mixtureInit[1].")]
        with self.assertRaisesRegex(ValueError,"noncontiguous"):f.compare()

    def test_invalid_selection_rejected(self):
        f=self.fixture()
        for args in ({"time_index":-1},{"time_index":5},{"phase":"bogus"}):
            with self.subTest(args=args),self.assertRaises(ValueError):f.compare(**args)

    def test_physical_failure_does_not_become_numerical_disagreement(self):
        f=self.fixture("FourField")
        f.metadata["solver"][1]["physical_diagnostics"]={"physical_consistency":False,"area_error":.1}
        report=f.compare()
        self.assertTrue(report["numerical_agreement"])
        self.assertEqual(report["reported_physical_consistency_failures"],["solver"])

    def test_missing_property_version_cannot_match_missing_version(self):
        f=self.fixture();del f.manifest["runtime"]["coolprop"]
        del f.metadata["solver"][1]["versions"]["CoolProp"]
        with self.assertRaisesRegex(ValueError,"CoolProp versions"):f.compare()

    def test_self_consistent_wrong_commit_is_not_pinned_source(self):
        f=self.fixture();f.manifest["upstream"]["git_commit"]="c"*40
        f.manifest["upstream"]["expected_commit"]="c"*40
        f.metadata["solver"][1]["upstream_commit"]="c"*40
        with self.assertRaisesRegex(ValueError,"Source commit"):f.compare()

    def test_actual_twofluid_classname_schema_alias(self):
        f=self.fixture("TwoFluid");f.metadata["solver"][1]["framework"]="TwoFluidSolver"
        del f.metadata["solver"][1]["schema"]
        self.assertTrue(f.compare()["passed"])


if __name__=="__main__":unittest.main()
