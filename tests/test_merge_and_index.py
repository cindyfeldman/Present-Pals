import json
import tempfile
import unittest
from pathlib import Path

from search_engine.merge_pipeline import clean_text, flatten_categories, normalize_products, merge_and_write
from search_engine.tfidf_index import IndexPaths, TfidfIndex


class MergeAndIndexTests(unittest.TestCase):
    def test_clean_text_strips_html(self):
        self.assertEqual(clean_text("Hello<br>world"), "Hello world")

    def test_flatten_categories_drops_target_label(self):
        cats = [{"name": "Target"}, {"name": "Home"}, {"name": "Kitchen"}]
        self.assertEqual(flatten_categories(cats), ["Home", "Kitchen"])

    def test_normalize_products_has_expected_fields(self):
        raw = [
            {
                "id": 1,
                "name": "Test Product",
                "url": "https://example.com",
                "price": 12.34,
                "description": "desc",
                "categories": [{"name": "Target"}, {"name": "Home"}],
            }
        ]
        norm = normalize_products(raw, "target")
        self.assertEqual(len(norm), 1)
        rec = norm[0]
        for key in ["doc_id", "source", "id", "name", "url", "price", "description", "categories", "category_path", "text"]:
            self.assertIn(key, rec)
        self.assertIn("Test Product", rec["text"])

    def test_build_index_small_docs(self):
        docs = [
            {"doc_id": "bestbuy-1", "source": "bestbuy", "id": 1, "name": "Knife Set", "price": 30.0, "url": "u", "category_path": ["Kitchen"], "text": "knife set kitchen"},
            {"doc_id": "target-2", "source": "target", "id": 2, "name": "Gaming Headset", "price": 40.0, "url": "u2", "category_path": ["Video Games"], "text": "gaming headset xbox"},
        ]

        with tempfile.TemporaryDirectory() as td:
            idx_dir = Path(td) / "index"
            index = TfidfIndex(IndexPaths(idx_dir))
            index.build_from_docs(docs)

            self.assertTrue(index.exists())
            self.assertGreaterEqual(len(index.meta), 2)

            results = index.query(user_query="knife", persona_terms=[], k=3)
            self.assertTrue(results)
            self.assertEqual(results[0].doc_id, "bestbuy-1")


if __name__ == "__main__":
    unittest.main()

