import unittest
from pathlib import Path

from powerbi_report_server_smith.audit.ai_readiness import score_ai_readiness
from powerbi_report_server_smith.audit.naming import audit_naming
from powerbi_report_server_smith.audit.relationships import relationship_gap_report
from powerbi_report_server_smith.audit.star_schema import audit_star_schema
from powerbi_report_server_smith.tmdl.loader import load_semantic_model

EXAMPLE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "SampleProject.SemanticModel"


class StarSchemaAuditTests(unittest.TestCase):
    def setUp(self):
        self.model = load_semantic_model(str(EXAMPLE_ROOT / "definition"))
        self.report = audit_star_schema(self.model)

    def test_classifications(self):
        self.assertEqual(self.report.classifications["Sales"], "fact")
        self.assertEqual(self.report.classifications["Customer"], "dimension")
        self.assertEqual(self.report.classifications["Product"], "dimension")
        self.assertEqual(self.report.classifications["Calendar"], "date")
        self.assertEqual(self.report.classifications["Notes"], "disconnected")

    def test_flags_disconnected_table(self):
        messages = [f.message for f in self.report.findings if f.table == "Notes"]
        self.assertTrue(any("No relationships" in m for m in messages))

    def test_score_is_reasonable_for_mostly_clean_model(self):
        self.assertGreaterEqual(self.report.score, 70)


class NamingAuditTests(unittest.TestCase):
    def test_flags_bad_column_name(self):
        model = load_semantic_model(str(EXAMPLE_ROOT / "definition"))
        report = audit_naming(model)
        flagged_names = {i.name for i in report.issues}
        self.assertIn("prod_nm", flagged_names)
        self.assertEqual(report.rename_plan.get("Product.prod_nm"), "ProdNm")

    def test_does_not_flag_clean_names(self):
        model = load_semantic_model(str(EXAMPLE_ROOT / "definition"))
        report = audit_naming(model)
        flagged_names = {i.name for i in report.issues}
        self.assertNotIn("CustomerName", flagged_names)


class RelationshipGapReportTests(unittest.TestCase):
    def test_finds_disconnected_table_and_no_missing_date_table(self):
        model = load_semantic_model(str(EXAMPLE_ROOT / "definition"))
        classifications = audit_star_schema(model).classifications
        report = relationship_gap_report(model, classifications)
        self.assertIn("Notes", report.disconnected_tables)
        self.assertFalse(report.missing_date_table)


class AiReadinessTests(unittest.TestCase):
    def test_score_reflects_partial_description_coverage(self):
        model = load_semantic_model(str(EXAMPLE_ROOT / "definition"))
        classifications = audit_star_schema(model).classifications
        report = score_ai_readiness(model, classifications, str(EXAMPLE_ROOT))
        # Sample project deliberately has some but not all descriptions set.
        self.assertGreater(report.table_description_coverage, 0)
        self.assertLess(report.table_description_coverage, 1)
        self.assertFalse(report.has_copilot_config)


if __name__ == "__main__":
    unittest.main()
