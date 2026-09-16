import shutil
import tempfile
import unittest
from pathlib import Path

from powerbi_report_server_smith.tmdl.loader import load_semantic_model, resolve_project_paths
from powerbi_report_server_smith.tmdl.writer import (
    append_relationship_block,
    set_description,
    set_property,
)

EXAMPLE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "SampleProject.SemanticModel"


class TmdlLoaderTests(unittest.TestCase):
    def test_loads_all_tables(self):
        model = load_semantic_model(str(EXAMPLE_ROOT / "definition"))
        self.assertEqual(
            set(model.tables.keys()),
            {"Sales", "Customer", "Product", "Calendar", "Notes"},
        )

    def test_loads_relationships(self):
        model = load_semantic_model(str(EXAMPLE_ROOT / "definition"))
        self.assertEqual(len(model.relationships), 3)
        r = model.relationships[0]
        self.assertEqual((r.from_table, r.from_column), ("Sales", "CustomerKey"))
        self.assertEqual((r.to_table, r.to_column), ("Customer", "CustomerKey"))

    def test_description_and_column_parsing(self):
        model = load_semantic_model(str(EXAMPLE_ROOT / "definition"))
        self.assertEqual(model.tables["Customer"].description,
                          "Customer master data — one row per customer")
        self.assertEqual(model.tables["Customer"].columns["CustomerName"].description,
                          "Customer's full legal name")
        self.assertTrue(model.tables["Customer"].columns["CustomerKey"].is_key)

    def test_resolve_project_paths_accepts_multiple_entry_points(self):
        d1, r1 = resolve_project_paths(str(EXAMPLE_ROOT))
        d2, r2 = resolve_project_paths(str(EXAMPLE_ROOT / "definition"))
        self.assertEqual(d1, d2)
        self.assertEqual(r1, r2)


class TmdlWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        shutil.copytree(EXAMPLE_ROOT, Path(self.tmpdir) / "SampleProject.SemanticModel")
        self.root = Path(self.tmpdir) / "SampleProject.SemanticModel"
        self.definition_dir = self.root / "definition"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_set_description_round_trips(self):
        path = self.definition_dir / "tables" / "Product.tmdl"
        text = path.read_text(encoding="utf-8")
        text = set_description(text, "table ", "Product", "Product master data")
        path.write_text(text, encoding="utf-8")

        model = load_semantic_model(str(self.definition_dir))
        self.assertEqual(model.tables["Product"].description, "Product master data")

    def test_set_property_round_trips(self):
        path = self.definition_dir / "tables" / "Product.tmdl"
        text = path.read_text(encoding="utf-8")
        text = set_property(text, "column ", "Category", "displayFolder", "Dim")
        path.write_text(text, encoding="utf-8")

        model = load_semantic_model(str(self.definition_dir))
        self.assertEqual(model.tables["Product"].columns["Category"].display_folder, "Dim")

    def test_append_relationship_round_trips(self):
        path = self.definition_dir / "relationships.tmdl"
        text = path.read_text(encoding="utf-8")
        text = append_relationship_block(text, "test-rel-id", "Notes", "CustomerKey", "Customer", "CustomerKey")
        path.write_text(text, encoding="utf-8")

        model = load_semantic_model(str(self.definition_dir))
        self.assertEqual(len(model.relationships), 4)
        self.assertTrue(any(r.id == "test-rel-id" for r in model.relationships))


if __name__ == "__main__":
    unittest.main()
