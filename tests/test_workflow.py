import shutil
import tempfile
import unittest
from pathlib import Path

from powerbi_report_server_smith import workflow

EXAMPLE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "SampleProject.SemanticModel"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir) / "SampleProject.SemanticModel"
        shutil.copytree(EXAMPLE_ROOT, self.root)
        self.definition_dir = self.root / "definition"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_staging_and_group_bookkeeping(self):
        workflow.label_new_query_stage(str(self.root), "Customer")
        workflow.label_new_query_stage(str(self.root), "Notes")
        self.assertEqual(set(workflow.list_staging_queries(str(self.root))), {"Customer", "Notes"})

        workflow.create_query_group(str(self.root), "Dim")
        self.assertIn("Dim", workflow.list_query_groups(str(self.root)))

    def test_promotion_blocked_for_disconnected_table(self):
        result = workflow.promote_staging_to_group(
            str(self.root), str(self.definition_dir), "Notes", "Dim"
        )
        self.assertFalse(result["promoted"])
        self.assertTrue(result["blocked_by"])

    def test_promotion_succeeds_for_clean_dimension(self):
        result = workflow.promote_staging_to_group(
            str(self.root), str(self.definition_dir), "Customer", "Dim"
        )
        self.assertTrue(result["promoted"])
        groups = workflow.list_query_groups(str(self.root))
        self.assertIn("Customer", groups["Dim"])

        # displayFolder should now be set on the promoted table's columns.
        table_file = self.definition_dir / "tables" / "Customer.tmdl"
        self.assertIn("displayFolder: Dim", table_file.read_text(encoding="utf-8"))

    def test_force_overrides_the_gate(self):
        result = workflow.promote_staging_to_group(
            str(self.root), str(self.definition_dir), "Notes", "Dim", force=True
        )
        self.assertTrue(result["promoted"])


if __name__ == "__main__":
    unittest.main()
