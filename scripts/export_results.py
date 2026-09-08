"""Export inspectable local results without copying PDFs into the repository."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crosscheck.db import Store  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Crosscheck results from a SQLite database.")
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/crosscheck-results.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    store = Store(args.database)
    try:
        payload = {
            "documents": [document.model_dump(mode="json") for document in store.documents()],
            "facts": [fact.model_dump(mode="json") for fact in store.facts()],
            "relationships": [relationship.model_dump(mode="json") for relationship in store.relationships()],
        }
    finally:
        store.close()
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
