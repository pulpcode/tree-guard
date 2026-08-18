from __future__ import annotations
import ast,json,tempfile,unittest
from pathlib import Path
from treeguard import load_tree_export
from treeguard.navigation_copilot_sealed_validation import SealedScenario
from treeguard.workbench import build_tree_reference_index
from scripts.navigation_copilot_b03c_c3.author_phase2a import author
from scripts.navigation_copilot_b03c_c3.record_phase2a_reviews import record
from scripts.navigation_copilot_b03c_c3.verify_phase2a import verify

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
    def test_exact_counts_and_no_phase2b(self):
        r=json.loads((C3/"phase2a-preflight.v1.json").read_bytes());self.assertEqual((736,56,48,42,6,8,16),(r["nodes"],r["candidates"],r["execution_scenarios"],r["target_present"],r["target_absent"],r["wrong_context"],r["repeat_subset"]));self.assertEqual([],r["blocking_finding_codes"]);self.assertFalse(any(C3.glob("*oracle*")));self.assertFalse(any(C3.glob("*manifest*")))
if __name__=="__main__":unittest.main()
