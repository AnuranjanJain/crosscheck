"""Run a reproducible local processing benchmark for one or more PDFs."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crosscheck.db import Store  # noqa: E402
from crosscheck.pipeline import process_pdf  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure Crosscheck processing for local PDFs.")
    parser.add_argument("pdf", nargs="+", type=Path)
    parser.add_argument("--database", default="outputs/evaluation.db")
    args = parser.parse_args()
    started = time.perf_counter()
    store = Store(args.database)
    try:
        for source in args.pdf:
            process_pdf(source, store)
        elapsed = time.perf_counter() - started
        print({
            "documents": len(store.documents()),
            "facts": len(store.facts()),
            "relationships": len(store.relationships()),
            "elapsed_seconds": round(elapsed, 2),
        })
    finally:
        store.close()


if __name__ == "__main__":
    main()
