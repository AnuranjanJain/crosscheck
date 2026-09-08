"""Validate reviewed evaluation label files against schema and PDF page text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"
LABELS = EVAL / "labels"
SCHEMA_PATH = EVAL / "schema.json"
STARTER = ROOT / "data" / "starter-datasets" / "starter-datasets"

DATASET_DIRS = {
    "delhivery": STARTER / "delhivery",
    "india-macroeconomy": STARTER / "india-macroeconomy",
}

REQUIRED_SPLITS = {
    ("delhivery", "development"),
    ("delhivery", "held_out"),
    ("india-macroeconomy", "development"),
    ("india-macroeconomy", "held_out"),
}


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_against_schema(payload: dict, schema: dict, path: Path, errors: list[str]) -> None:
    try:
        import jsonschema
    except ImportError:
        # Lightweight fallback when jsonschema is not installed.
        for key in schema.get("required", []):
            if key not in payload:
                errors.append(f"{path.name}: missing required key {key}")
        if not isinstance(payload.get("facts"), list) or len(payload.get("facts", [])) < 20:
            errors.append(f"{path.name}: facts must be a list with >= 20 items")
        if not isinstance(payload.get("relationships"), list) or len(payload.get("relationships", [])) < 8:
            errors.append(f"{path.name}: relationships must be a list with >= 8 items")
        return

    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"{path.name}: schema validation failed: {exc.message}")


def page_text(pdf_path: Path, page_index: int, cache: dict[tuple[str, int], str]) -> str:
    key = (str(pdf_path), page_index)
    if key in cache:
        return cache[key]
    with pdfplumber.open(pdf_path) as pdf:
        if page_index < 0 or page_index >= len(pdf.pages):
            raise IndexError(f"page_index {page_index} out of range for {pdf_path.name}")
        text = pdf.pages[page_index].extract_text() or ""
    cache[key] = text
    return text


def validate_label_file(path: Path, schema: dict, errors: list[str], warnings: list[str]) -> None:
    payload = load_json(path)
    if not isinstance(payload, dict):
        errors.append(f"{path.name}: root must be an object")
        return

    validate_against_schema(payload, schema, path, errors)

    dataset = payload.get("dataset")
    split = payload.get("split")
    facts = payload.get("facts") or []
    relationships = payload.get("relationships") or []

    if (dataset, split) not in REQUIRED_SPLITS:
        errors.append(f"{path.name}: unexpected dataset/split pair {dataset!r}/{split!r}")

    fact_ids = []
    seen_ids: set[str] = set()
    pdf_cache: dict[tuple[str, int], str] = {}
    dataset_dir = DATASET_DIRS.get(dataset)

    for fact in facts:
        fact_id = fact.get("id")
        if not fact_id:
            errors.append(f"{path.name}: fact missing id")
            continue
        if fact_id in seen_ids:
            errors.append(f"{path.name}: duplicate fact id {fact_id}")
        seen_ids.add(fact_id)
        fact_ids.append(fact_id)

        filename = fact.get("document_filename")
        page_index = fact.get("pdf_page_index")
        quote = fact.get("evidence_quote")
        if dataset_dir is None:
            errors.append(f"{path.name}: unknown dataset directory for {dataset}")
            continue
        pdf_path = dataset_dir / filename
        if not pdf_path.exists():
            errors.append(f"{path.name}: missing PDF {filename} for fact {fact_id}")
            continue
        try:
            text = page_text(pdf_path, int(page_index), pdf_cache)
        except Exception as exc:  # noqa: BLE001 - collect and continue
            errors.append(f"{path.name}: fact {fact_id} page load failed: {exc}")
            continue
        if quote not in text:
            # Allow exact contiguous match after normalizing CRLF only.
            if quote.replace("\r\n", "\n") not in text.replace("\r\n", "\n"):
                errors.append(
                    f"{path.name}: fact {fact_id} evidence_quote not found on page_index {page_index} of {filename}"
                )

    fact_id_set = set(fact_ids)
    for rel in relationships:
        rel_id = rel.get("id")
        left = rel.get("left_fact_id")
        right = rel.get("right_fact_id")
        label = rel.get("expected_label")
        if left not in fact_id_set or right not in fact_id_set:
            errors.append(f"{path.name}: relationship {rel_id} references unknown fact ids")
        if left == right:
            errors.append(f"{path.name}: relationship {rel_id} compares a fact to itself")
        if label == "likely_contradiction":
            warnings.append(
                f"{path.name}: relationship {rel_id} is labeled likely_contradiction; confirm this is not a period/unit/scope/vintage difference."
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels-dir",
        type=Path,
        default=LABELS,
        help="Directory containing label JSON files",
    )
    args = parser.parse_args(argv)

    if not SCHEMA_PATH.exists():
        print(f"missing schema: {SCHEMA_PATH}", file=sys.stderr)
        return 2
    if not args.labels_dir.exists():
        print(f"missing labels dir: {args.labels_dir}", file=sys.stderr)
        return 2

    schema = load_json(SCHEMA_PATH)
    label_files = sorted(args.labels_dir.glob("*.json"))
    if not label_files:
        print(f"no label files in {args.labels_dir}", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()

    for path in label_files:
        payload = load_json(path)
        if isinstance(payload, dict):
            seen_pairs.add((payload.get("dataset"), payload.get("split")))
        validate_label_file(path, schema, errors, warnings)

    missing = REQUIRED_SPLITS - seen_pairs
    for dataset, split in sorted(missing):
        errors.append(f"missing required label file for {dataset}/{split}")

    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} error(s), {len(label_files)} file(s) checked", file=sys.stderr)
        return 1

    print(f"OK: validated {len(label_files)} label file(s)")
    for path in label_files:
        payload = load_json(path)
        print(
            f"  {path.name}: facts={len(payload['facts'])} relationships={len(payload['relationships'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
