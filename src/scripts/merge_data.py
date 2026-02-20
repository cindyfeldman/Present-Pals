import json
import sys
from pathlib import Path

# Allow importing search_engine when run from any working directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from search_engine.merge_pipeline import merge_and_write


SRC_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = SRC_DIR / "json"
OUT_DIR = SRC_DIR / "data"

BESTBUY_PATH = RAW_DIR / "complete_product_list.json"
TARGET_PATH = RAW_DIR / "target_data_set.json"
AMAZON_PATH = RAW_DIR / "amazon-products.csv"
WALMART_PATH = RAW_DIR / "walmart-products.csv"
OUT_PATH = OUT_DIR / "products_clean.json"


def main() -> None:
    if not BESTBUY_PATH.exists():
        raise FileNotFoundError(f"Missing: {BESTBUY_PATH}")
    if not TARGET_PATH.exists():
        raise FileNotFoundError(f"Missing: {TARGET_PATH}")

    merged = merge_and_write(
        bestbuy_path=BESTBUY_PATH,
        target_path=TARGET_PATH,
        out_path=OUT_PATH,
        additional_sources={"amazon": AMAZON_PATH, "walmart": WALMART_PATH},
    )

    print(f"Merged records: {len(merged)}")
    if merged:
        print("\nSample record:\n", json.dumps(merged[0], indent=2))


if __name__ == "__main__":
    main()
