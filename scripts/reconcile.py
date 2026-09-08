"""Rebuild relationship labels after a comparison-rule update."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crosscheck.compare import candidate_pairs  # noqa: E402
from crosscheck.db import Store  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Crosscheck relationships from existing facts.")
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    store = Store(args.database)
    try:
        store.clear_relationships()
        for relationship in candidate_pairs(store.facts()):
            store.save_relationship(relationship)
        print({"relationships": len(store.relationships())})
    finally:
        store.close()


if __name__ == "__main__":
    main()
