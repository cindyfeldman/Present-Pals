import unittest
import tempfile
from pathlib import Path

from search_engine.indexed_engine import IndexedGiftSearch
from search_engine.tfidf_index import IndexPaths, TfidfIndex


class IndexedEngineIntegrationTests(unittest.TestCase):
    def test_indexed_search_runs_on_repo_data(self):
        """
        Integration test against repo JSON data, but uses a limited index build
        to keep runtime reasonable.
        """
        engine = IndexedGiftSearch(repo_root=Path(__file__).resolve().parents[1])

        # Force a fresh index build in a temp dir so the test isn't affected
        # by whatever index artifacts happen to exist in src/index/.
        with tempfile.TemporaryDirectory() as td:
            engine.index = TfidfIndex(IndexPaths(Path(td) / "index"))
            engine.ensure_index(max_docs=2000)

            res = engine.search_from_form(
                form_data={
                    "interests": ["Cooking"],
                    "tech_level": "medium",
                    "budget": "medium",
                    "occasion": "Wedding",
                },
                user_query="knife",
                recipient_key="mom",
                k=5,
                debug=False,
            )

            self.assertTrue(res["success"])
            self.assertGreater(
                len(res["results"]),
                0,
                "No results returned. If this is flaky, increase max_docs or adjust query.",
            )

            top_name = res["results"][0]["product"]["name"].lower()
            # Not guaranteed, but very likely with this dataset. If it fails, index/sample changed.
            self.assertTrue(("knife" in top_name) or ("cut" in top_name))


if __name__ == "__main__":
    unittest.main()

