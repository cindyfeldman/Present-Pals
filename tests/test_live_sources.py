import json
import tempfile
import unittest
from pathlib import Path

from search_engine.merge_pipeline import merge_and_write


class LiveSourcesTests(unittest.TestCase):
    def test_ebay_snapshot_is_included_in_merge(self):
        """
        Verify that when an eBay snapshot JSON is provided, merge_and_write()
        includes those products in the merged corpus with source='ebay'.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)

            # Minimal fake BestBuy / Target inputs
            bestbuy_path = tmp / "bestbuy.json"
            target_path = tmp / "target.json"
            ebay_path = tmp / "ebay_products.json"
            out_path = tmp / "merged.json"

            bestbuy_items = [
                {
                    "id": 1,
                    "name": "BestBuy Knife Set",
                    "url": "https://bestbuy.example/knife",
                    "price": 29.99,
                    "description": "A nice knife set from BestBuy.",
                    "categories": [{"name": "Target"}, {"name": "Kitchen"}],
                }
            ]
            target_items = [
                {
                    "id": 2,
                    "name": "Target Cutting Board",
                    "url": "https://target.example/board",
                    "price": 19.99,
                    "description": "A sturdy cutting board from Target.",
                    "categories": [{"name": "Target"}, {"name": "Kitchen"}],
                }
            ]

            # Fake eBay snapshot in the "raw-ish" format that normalize_live_products expects
            ebay_items = [
                {
                    "id": "EBAY-123",
                    "name": "eBay Chef Knife",
                    "url": "https://ebay.example/chef-knife",
                    "price": 24.5,
                    "description": "A sharp chef knife from eBay.",
                    "category_path": ["Kitchen", "Cutlery"],
                }
            ]

            bestbuy_path.write_text(json.dumps(bestbuy_items), encoding="utf-8")
            target_path.write_text(json.dumps(target_items), encoding="utf-8")
            ebay_path.write_text(json.dumps(ebay_items), encoding="utf-8")

            merged = merge_and_write(
                bestbuy_path=bestbuy_path,
                target_path=target_path,
                out_path=out_path,
                amazon_csv_path=None,
                walmart_csv_path=None,
                ebay_snapshot_path=ebay_path,
            )

            # We expect 3 records total (1 BestBuy, 1 Target, 1 eBay)
            self.assertEqual(3, len(merged))

            sources = {p["source"] for p in merged}
            self.assertIn("ebay", sources)

            # Find the eBay record and sanity‑check its shape
            ebay_docs = [p for p in merged if p["source"] == "ebay"]
            self.assertEqual(1, len(ebay_docs))
            ebay_doc = ebay_docs[0]
            self.assertTrue(str(ebay_doc["doc_id"]).startswith("ebay-"))
            self.assertIn("eBay Chef Knife", ebay_doc["name"])
            self.assertGreater(ebay_doc["price"], 0)
            self.assertIn("Kitchen", ebay_doc.get("category_path", []))


if __name__ == "__main__":
    unittest.main()

