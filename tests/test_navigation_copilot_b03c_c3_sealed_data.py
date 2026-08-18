from __future__ import annotations
import ast,json,shutil,tempfile,unittest
from pathlib import Path
from treeguard import load_tree_export
from treeguard.navigation_copilot_sealed_validation import SealedScenario
from treeguard.workbench import build_tree_reference_index
from scripts.navigation_copilot_b03c_c3.author_phase2a import author
from scripts.navigation_copilot_b03c_c3.record_phase2a_reviews import record
from scripts.navigation_copilot_b03c_c3.verify_phase2a import verify
from scripts.navigation_copilot_b03c_c3.verify_phase2b import Phase2BError,freeze_phase2b,materialize_private_preflight_bundle,reviewed_bytes_digest

ROOT=Path(__file__).resolve().parents[1];C2=ROOT/"tests/fixtures/fictional/navigation_copilot_sealed_v3c_b03c_c2";C3=ROOT/"tests/fixtures/fictional/navigation_copilot_sealed_v3c_b03c_c3"
AUTHOR=ROOT/"scripts/navigation_copilot_b03c_c3/author_phase2a.py";REVIEW=ROOT/"scripts/navigation_copilot_b03c_c3/record_phase2a_reviews.py";VERIFY=ROOT/"scripts/navigation_copilot_b03c_c3/verify_phase2a.py"

class B03C3Phase2ATest(unittest.TestCase):
    def test_three_producers_are_physically_separated(self):
        def imports(path):
            tree=ast.parse(path.read_text());return {alias.name for node in ast.walk(tree) if isinstance(node,(ast.Import,ast.ImportFrom)) for alias in node.names}
        self.assertFalse(any("record_phase2a_reviews" in name for name in imports(AUTHOR)))
        self.assertFalse(any("author_phase2a" in name for name in imports(REVIEW)))
        self.assertFalse(any("record_phase2a_reviews" in name for name in imports(VERIFY)))
        packet=json.loads((C3/"review-packet.v1.json").read_bytes());self.assertTrue(all(x["review_state"]=="PENDING" for x in packet["items"]))
    def test_deterministic_rebuild_and_runtime_refs(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);author(C2,p);record(p/"tree.json",p/"candidate-scenarios.v2.json",p/"review-packet.v1.json",C2/"review-decisions.hidden.v1.json",p/"review-decisions.hidden.v1.json");verify(p,p/"scenarios.v2.json",p/"phase2a-preflight.v1.json")
            for name in ("tree.json","candidate-scenarios.v2.json","review-packet.v1.json","review-decisions.hidden.v1.json","scenarios.v2.json","phase2a-preflight.v1.json"):self.assertEqual((C3/name).read_bytes(),(p/name).read_bytes())
        result=load_tree_export(C3/"tree.json");refs=build_tree_reference_index(result.tree);items=[SealedScenario.from_dict(x) for x in json.loads((C3/"scenarios.v2.json").read_bytes())];parents=[x.proposed_parent_ref for x in items if x.proposed_parent_ref];self.assertEqual(8,len(parents));self.assertTrue(all(x in refs.node_id_by_ref and not x.startswith("N500") for x in parents))
    def test_exact_counts_and_phase2b_remains_nonexecuting(self):
        r=json.loads((C3/"phase2a-preflight.v1.json").read_bytes());self.assertEqual((736,56,48,42,6,8,16),(r["nodes"],r["candidates"],r["execution_scenarios"],r["target_present"],r["target_absent"],r["wrong_context"],r["repeat_subset"]));self.assertEqual([],r["blocking_finding_codes"]);self.assertTrue((C3/"hidden-oracle.v2.json").is_file());self.assertTrue((C3/"freeze-report.v1.json").is_file());self.assertFalse(any(C3.glob("*execution*manifest*")));self.assertFalse(any(C3.glob("*model*response*")))

class B03C3Phase2BTest(unittest.TestCase):
    def test_freeze_is_deterministic_and_maps_runtime_refs_back_to_stable_ids(self):
        with tempfile.TemporaryDirectory() as first,tempfile.TemporaryDirectory() as second:
            a=Path(first)/"fixture";b=Path(second)/"fixture";shutil.copytree(C3,a);shutil.copytree(C3,b)
            ar=freeze_phase2b(a,a/"hidden-oracle.v2.json",a/"freeze-report.v1.json");br=freeze_phase2b(b,b/"hidden-oracle.v2.json",b/"freeze-report.v1.json")
            self.assertEqual(ar,br);self.assertEqual("PASS",ar["runner_collection_validation"]);self.assertEqual(8,ar["wrong_context_forbidden_stable_ids"]);self.assertEqual((a/"hidden-oracle.v2.json").read_bytes(),(b/"hidden-oracle.v2.json").read_bytes())
        refs=build_tree_reference_index(load_tree_export(C3/"tree.json").tree);scenarios={x["scenario_ref"]:SealedScenario.from_dict(x) for x in json.loads((C3/"scenarios.v2.json").read_bytes())};oracles=json.loads((C3/"hidden-oracle.v2.json").read_bytes())
        challenged=[x for x in oracles if x["wrong_context_challenge"]];self.assertEqual(8,len(challenged))
        for oracle in challenged:
            scenario=scenarios[oracle["scenario_ref"]];self.assertEqual([refs.node_id_by_ref[scenario.proposed_parent_ref]],oracle["forbidden_node_ids"]);self.assertTrue(oracle["forbidden_node_ids"][0].startswith("N500"))
    def test_oracle_sources_and_categories_are_exact(self):
        scenarios=[SealedScenario.from_dict(x) for x in json.loads((C3/"scenarios.v2.json").read_bytes())];decisions={x["scenario_ref"]:x for x in json.loads((C3/"review-decisions.hidden.v1.json").read_bytes())["decisions"]};oracles=json.loads((C3/"hidden-oracle.v2.json").read_bytes())
        for scenario,oracle in zip(scenarios,oracles,strict=True):
            self.assertEqual(reviewed_bytes_digest((C3/"tree.json").read_bytes(),scenario,decisions[scenario.scenario_ref]),oracle["reviewed_bytes_digest"])
            if scenario.category=="WEAK_EVIDENCE":self.assertEqual(("LIMIT",["NEED_EVIDENCE"],"EXIT",None,"PRESENT_NOT_FOUND"),(oracle["expected_route"],oracle["acceptable_policy_statuses"],oracle["acceptable_terminals"][0]["action"],oracle["acceptable_terminals"][0]["target_node_id"],oracle["acceptable_terminals"][0]["target_disposition"]))
            elif scenario.category=="CLARIFICATION":self.assertEqual(("CLARIFY",["NEED_EVIDENCE"]),(oracle["expected_route"],oracle["acceptable_policy_statuses"]))
            elif scenario.category=="TARGET_ABSENT":self.assertEqual(([],["NONE"],"ABSENT"),(oracle["acceptable_node_ids"],oracle["acceptable_policy_statuses"],oracle["acceptable_terminals"][0]["target_disposition"]))
    def test_source_drift_and_execution_leak_fail_closed(self):
        for name in ("blueprint.v1.json","tree.json","candidate-scenarios.v2.json","review-packet.v1.json","review-decisions.hidden.v1.json","scenarios.v2.json","phase2a-preflight.v1.json"):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                copied=Path(directory)/"fixture";shutil.copytree(C3,copied);(copied/name).write_bytes((copied/name).read_bytes()+b" ")
                with self.assertRaises(Phase2BError) as caught:freeze_phase2b(copied,copied/"hidden-oracle.v2.json",copied/"freeze-report.v1.json")
                self.assertEqual("DATASET_NONDETERMINISTIC",caught.exception.code)
        with tempfile.TemporaryDirectory() as directory:
            copied=Path(directory)/"fixture";shutil.copytree(C3,copied);(copied/"execution-manifest.v2.json").write_text("{}")
            with self.assertRaises(Phase2BError) as caught:freeze_phase2b(copied,copied/"hidden-oracle.v2.json",copied/"freeze-report.v1.json")
            self.assertEqual("DATASET_ORACLE_LEAK",caught.exception.code)
    def test_output_conflict_and_symlink_do_not_publish_partial_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            copied=Path(directory)/"fixture";shutil.copytree(C3,copied);tree=copied/"tree.json";tree.unlink();tree.symlink_to(C3/"tree.json")
            with self.assertRaises(Phase2BError) as caught:freeze_phase2b(copied,copied/"new-oracle.json",copied/"new-report.json")
            self.assertEqual("DATASET_REFERENCE_INVALID",caught.exception.code)
        with tempfile.TemporaryDirectory() as directory:
            copied=Path(directory)/"fixture";shutil.copytree(C3,copied);oracle=copied/"new-oracle.json";report=copied/"new-report.json";report.write_text("{}")
            with self.assertRaises(Phase2BError) as caught:freeze_phase2b(copied,oracle,report)
            self.assertEqual("DATASET_NONDETERMINISTIC",caught.exception.code);self.assertFalse(oracle.exists())
        with tempfile.TemporaryDirectory() as directory:
            copied=Path(directory)/"fixture";shutil.copytree(C3,copied);outside=Path(directory)/"outside.json";oracle=copied/"new-oracle.json";oracle.symlink_to(outside)
            with self.assertRaises(Phase2BError) as caught:freeze_phase2b(copied,oracle,copied/"new-report.json")
            self.assertEqual("DATASET_REFERENCE_INVALID",caught.exception.code);self.assertFalse(outside.exists())
    def test_private_preflight_bundle_is_disposable_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"bundle";manifest,oracle=materialize_private_preflight_bundle(C3,root)
            self.assertEqual(0o700,root.stat().st_mode&0o777);self.assertEqual(0o600,manifest.stat().st_mode&0o777);self.assertEqual(0o600,oracle.stat().st_mode&0o777)
            self.assertEqual((C3/"hidden-oracle.v2.json").read_bytes(),oracle.read_bytes());self.assertFalse((C3/"preflight-manifest.v2.json").exists())
if __name__=="__main__":unittest.main()
