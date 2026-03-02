import json
import tempfile
import unittest
from pathlib import Path

from search_engine.merge_pipeline import clean_text, flatten_categories, normalize_products, merge_and_write, parse_price
from search_engine.tfidf_index import IndexPaths, TfidfIndex


class MergeAndIndexTests(unittest.TestCase):
    def test_clean_text_strips_html(self):
        self.assertEqual(clean_text("Hello<br>world"), "Hello world")

    def test_flatten_categories_drops_target_label(self):
        cats = [{"name": "Target"}, {"name": "Home"}, {"name": "Kitchen"}]
        self.assertEqual(flatten_categories(cats), ["Home", "Kitchen"])

    def test_parse_price_handles_currency_strings(self):
        self.assertEqual(parse_price("$1,299.95"), 1299.95)
        self.assertEqual(parse_price("USD 42"), 42.0)
        self.assertIsNone(parse_price("N/A"))

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

    def test_merge_and_write_supports_additional_csv_sources(self):
        bestbuy_data = [
            {"id": 1, "name": "BestBuy Product", "url": "https://bestbuy.com/p/1", "price": 9.99, "description": "d", "categories": [{"name": "Electronics"}]}
        ]
        target_data = [
            {"id": 2, "name": "Target Product", "url": "https://target.com/p/2", "price": 14.99, "description": "d2", "categories": [{"name": "Target"}, {"name": "Home"}]}
        ]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            bestbuy_path = td_path / "bestbuy.json"
            target_path = td_path / "target.json"
            amazon_csv = td_path / "amazon-products.csv"
            out_path = td_path / "products_clean.json"

            bestbuy_path.write_text(json.dumps(bestbuy_data), encoding="utf-8")
            target_path.write_text(json.dumps(target_data), encoding="utf-8")
            amazon_csv.write_text(
                "title,product_url,price,seller_name,category\n"
                "Echo Dot,https://amazon.com/dp/abc,$49.99,Amazon,Smart Home > Speakers\n",
                encoding="utf-8",
            )

            merged = merge_and_write(
                bestbuy_path=bestbuy_path,
                target_path=target_path,
                out_path=out_path,
                additional_sources={"amazon": amazon_csv},
            )

            self.assertTrue(any(p["source"] == "amazon" for p in merged))
            self.assertTrue(any(p["name"] == "Echo Dot" for p in merged))
            self.assertTrue(out_path.exists())

    def test_walmart_csv_products_included(self):
        """Test that Walmart CSV products are properly merged with correct source."""
        bestbuy_data = [
            {"id": 1, "name": "BestBuy Product", "url": "https://bestbuy.com/p/1", "price": 9.99, "description": "d", "categories": [{"name": "Electronics"}]}
        ]
        target_data = [
            {"id": 2, "name": "Target Product", "url": "https://target.com/p/2", "price": 14.99, "description": "d2", "categories": [{"name": "Target"}, {"name": "Home"}]}
        ]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            bestbuy_path = td_path / "bestbuy.json"
            target_path = td_path / "target.json"
            walmart_csv = td_path / "walmart-products.csv"
            out_path = td_path / "products_clean.json"

            bestbuy_path.write_text(json.dumps(bestbuy_data), encoding="utf-8")
            target_path.write_text(json.dumps(target_data), encoding="utf-8")
            walmart_csv.write_text(
                "name,product_url,price,description,category\n"
                "Great Value Paper Plates,https://walmart.com/ip/123,4.99,Disposable plates for parties,Home > Kitchen > Dining\n"
                "Mainstays Bed Sheets,https://walmart.com/ip/456,19.99,Soft cotton bed sheets,Home > Bedding > Sheets\n",
                encoding="utf-8",
            )

            merged = merge_and_write(
                bestbuy_path=bestbuy_path,
                target_path=target_path,
                out_path=out_path,
                additional_sources={"walmart": walmart_csv},
            )

            # Verify Walmart products are included
            walmart_products = [p for p in merged if p["source"] == "walmart"]
            self.assertGreater(len(walmart_products), 0, "Should have Walmart products")
            self.assertTrue(any("Paper Plates" in p["name"] for p in walmart_products))
            self.assertTrue(any("Bed Sheets" in p["name"] for p in walmart_products))
            
            # Verify Walmart products have correct structure
            for walmart_product in walmart_products:
                self.assertEqual(walmart_product["source"], "walmart")
                self.assertIn("doc_id", walmart_product)
                self.assertTrue(walmart_product["doc_id"].startswith("walmart-"))

    def test_amazon_csv_products_included(self):
        """Test that Amazon CSV products are properly merged with correct source."""
        bestbuy_data = [
            {"id": 1, "name": "BestBuy Product", "url": "https://bestbuy.com/p/1", "price": 9.99, "description": "d", "categories": [{"name": "Electronics"}]}
        ]
        target_data = [
            {"id": 2, "name": "Target Product", "url": "https://target.com/p/2", "price": 14.99, "description": "d2", "categories": [{"name": "Target"}, {"name": "Home"}]}
        ]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            bestbuy_path = td_path / "bestbuy.json"
            target_path = td_path / "target.json"
            amazon_csv = td_path / "amazon-products.csv"
            out_path = td_path / "products_clean.json"

            bestbuy_path.write_text(json.dumps(bestbuy_data), encoding="utf-8")
            target_path.write_text(json.dumps(target_data), encoding="utf-8")
            amazon_csv.write_text(
                "title,product_url,price,description,category\n"
                "Fire TV Stick,https://amazon.com/dp/B08C1W5N87,39.99,Streaming media player,Electronics > Streaming Devices\n"
                "Echo Show 10,https://amazon.com/dp/B08K8NQ3J4,249.99,Smart display with Alexa,Electronics > Smart Home\n",
                encoding="utf-8",
            )

            merged = merge_and_write(
                bestbuy_path=bestbuy_path,
                target_path=target_path,
                out_path=out_path,
                additional_sources={"amazon": amazon_csv},
            )

            # Verify Amazon products are included
            amazon_products = [p for p in merged if p["source"] == "amazon"]
            self.assertGreater(len(amazon_products), 0, "Should have Amazon products")
            self.assertTrue(any("Fire TV Stick" in p["name"] for p in amazon_products))
            self.assertTrue(any("Echo Show" in p["name"] for p in amazon_products))
            
            # Verify Amazon products have correct structure
            for amazon_product in amazon_products:
                self.assertEqual(amazon_product["source"], "amazon")
                self.assertIn("doc_id", amazon_product)
                self.assertTrue(amazon_product["doc_id"].startswith("amazon-"))

    def test_target_json_products_included(self):
        """Test that Target JSON products are properly merged with correct source."""
        bestbuy_data = [
            {"id": 1, "name": "BestBuy Product", "url": "https://bestbuy.com/p/1", "price": 9.99, "description": "d", "categories": [{"name": "Electronics"}]}
        ]
        target_data = [
            {"id": "TGT-100", "name": "Target Brand T-Shirt", "url": "https://target.com/p/100", "price": 12.99, "description": "Comfortable cotton t-shirt", "categories": [{"name": "Target"}, {"name": "Clothing"}, {"name": "Men"}]},
            {"id": "TGT-200", "name": "Threshold Throw Pillow", "url": "https://target.com/p/200", "price": 24.99, "description": "Decorative pillow for living room", "categories": [{"name": "Target"}, {"name": "Home"}, {"name": "Decor"}]},
        ]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            bestbuy_path = td_path / "bestbuy.json"
            target_path = td_path / "target.json"
            out_path = td_path / "products_clean.json"

            bestbuy_path.write_text(json.dumps(bestbuy_data), encoding="utf-8")
            target_path.write_text(json.dumps(target_data), encoding="utf-8")

            merged = merge_and_write(
                bestbuy_path=bestbuy_path,
                target_path=target_path,
                out_path=out_path,
            )

            # Verify Target products are included
            target_products = [p for p in merged if p["source"] == "target"]
            self.assertEqual(len(target_products), 2, "Should have 2 Target products")
            self.assertTrue(any("T-Shirt" in p["name"] for p in target_products))
            self.assertTrue(any("Throw Pillow" in p["name"] for p in target_products))
            
            # Verify Target products have correct structure and categories
            for target_product in target_products:
                self.assertEqual(target_product["source"], "target")
                self.assertIn("doc_id", target_product)
                self.assertTrue(target_product["doc_id"].startswith("target-"))
                # Verify "Target" category is dropped from category_path
                self.assertNotIn("Target", target_product.get("category_path", []))

    def test_all_sources_included_in_full_merge(self):
        """Test that products from BestBuy, Target, Walmart, and Amazon are all included."""
        bestbuy_data = [
            {"id": 1, "name": "BestBuy Laptop", "url": "https://bestbuy.com/p/1", "price": 999.99, "description": "Gaming laptop", "categories": [{"name": "Electronics"}]},
            {"id": 2, "name": "BestBuy Headphones", "url": "https://bestbuy.com/p/2", "price": 79.99, "description": "Wireless headphones", "categories": [{"name": "Electronics"}]},
        ]
        target_data = [
            {"id": "TGT-1", "name": "Target Coffee Maker", "url": "https://target.com/p/1", "price": 49.99, "description": "Drip coffee maker", "categories": [{"name": "Target"}, {"name": "Kitchen"}]},
        ]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            bestbuy_path = td_path / "bestbuy.json"
            target_path = td_path / "target.json"
            walmart_csv = td_path / "walmart-products.csv"
            amazon_csv = td_path / "amazon-products.csv"
            out_path = td_path / "products_clean.json"

            bestbuy_path.write_text(json.dumps(bestbuy_data), encoding="utf-8")
            target_path.write_text(json.dumps(target_data), encoding="utf-8")
            walmart_csv.write_text(
                "name,product_url,price,description,category\n"
                "Walmart Brand Cereal,https://walmart.com/ip/1,3.99,Breakfast cereal,Food > Breakfast\n"
                "Walmart Storage Bins,https://walmart.com/ip/2,7.99,Plastic storage containers,Home > Storage\n",
                encoding="utf-8",
            )
            amazon_csv.write_text(
                "title,product_url,price,description,category\n"
                "Amazon Basics Batteries,https://amazon.com/dp/B001,8.99,AA batteries,Electronics > Batteries\n"
                "Kindle Paperwhite,https://amazon.com/dp/B002,139.99,E-reader,Electronics > E-Readers\n",
                encoding="utf-8",
            )

            merged = merge_and_write(
                bestbuy_path=bestbuy_path,
                target_path=target_path,
                out_path=out_path,
                additional_sources={"walmart": walmart_csv, "amazon": amazon_csv},
            )

            # Count products by source
            source_counts = {}
            for p in merged:
                source_counts[p["source"]] = source_counts.get(p["source"], 0) + 1

            # Verify all sources are present
            self.assertIn("bestbuy", source_counts, "Should have BestBuy products")
            self.assertIn("target", source_counts, "Should have Target products")
            self.assertIn("walmart", source_counts, "Should have Walmart products")
            self.assertIn("amazon", source_counts, "Should have Amazon products")

            # Verify counts match expectations
            self.assertEqual(source_counts["bestbuy"], 2, "Should have 2 BestBuy products")
            self.assertEqual(source_counts["target"], 1, "Should have 1 Target product")
            self.assertEqual(source_counts["walmart"], 2, "Should have 2 Walmart products")
            self.assertEqual(source_counts["amazon"], 2, "Should have 2 Amazon products")

            # Verify specific products exist
            self.assertTrue(any("Laptop" in p["name"] and p["source"] == "bestbuy" for p in merged))
            self.assertTrue(any("Coffee Maker" in p["name"] and p["source"] == "target" for p in merged))
            self.assertTrue(any("Cereal" in p["name"] and p["source"] == "walmart" for p in merged))
            self.assertTrue(any("Kindle" in p["name"] and p["source"] == "amazon" for p in merged))

    def test_csv_with_large_fields_handles_correctly(self):
        """Test that CSV files with very large description fields are handled correctly."""
        bestbuy_data = [
            {"id": 1, "name": "BestBuy Product", "url": "https://bestbuy.com/p/1", "price": 9.99, "description": "d", "categories": [{"name": "Electronics"}]}
        ]
        target_data = [
            {"id": 2, "name": "Target Product", "url": "https://target.com/p/2", "price": 14.99, "description": "d2", "categories": [{"name": "Target"}, {"name": "Home"}]}
        ]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            bestbuy_path = td_path / "bestbuy.json"
            target_path = td_path / "target.json"
            amazon_csv = td_path / "amazon-products.csv"
            out_path = td_path / "products_clean.json"

            bestbuy_path.write_text(json.dumps(bestbuy_data), encoding="utf-8")
            target_path.write_text(json.dumps(target_data), encoding="utf-8")
            
            # Create CSV with a very long description field (>131072 chars)
            long_description = "A" * 150000  # Exceeds default CSV field limit
            amazon_csv.write_text(
                "title,product_url,price,description,category\n"
                f"Test Product,https://amazon.com/dp/123,29.99,\"{long_description}\",Electronics\n",
                encoding="utf-8",
            )

            # Should not raise csv.Error about field size limit
            merged = merge_and_write(
                bestbuy_path=bestbuy_path,
                target_path=target_path,
                out_path=out_path,
                additional_sources={"amazon": amazon_csv},
            )

            # Verify product was loaded despite large field
            amazon_products = [p for p in merged if p["source"] == "amazon"]
            self.assertGreater(len(amazon_products), 0, "Should load product with large description field")
            self.assertEqual(len(amazon_products[0]["description"]), 150000, "Should preserve full description")


if __name__ == "__main__":
    unittest.main()
