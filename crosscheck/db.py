from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .models import Document, Evidence, Fact, ProcessingIssue, Relationship

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT UNIQUE NOT NULL, page_count INTEGER NOT NULL, status TEXT NOT NULL, warnings TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), page_index INTEGER NOT NULL, printed_page TEXT, text TEXT NOT NULL, heading TEXT, bbox TEXT, tables TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS facts (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), evidence_id TEXT NOT NULL REFERENCES evidence(id), subject TEXT NOT NULL, predicate TEXT NOT NULL, original_text TEXT NOT NULL, value_text TEXT, value_number REAL, unit TEXT, period TEXT, scope TEXT, status TEXT NOT NULL, attributes TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relationships (id TEXT PRIMARY KEY, left_fact_id TEXT NOT NULL REFERENCES facts(id), right_fact_id TEXT NOT NULL REFERENCES facts(id), kind TEXT NOT NULL, confidence REAL NOT NULL, explanation TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(left_fact_id, right_fact_id));
CREATE TABLE IF NOT EXISTS issues (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), page_index INTEGER, code TEXT NOT NULL, message TEXT NOT NULL, recoverable INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processing_config (document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE, config TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processing_runs (id TEXT PRIMARY KEY, filename TEXT NOT NULL, status TEXT NOT NULL, events TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: str | Path = "crosscheck.db") -> None:
        database_path = Path(path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(database_path))
        self.connection.row_factory = sqlite3.Row
        self._in_transaction = False
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        self._ensure_column("evidence", "tables", "TEXT NOT NULL DEFAULT '[]'")
        self.connection.commit()

    @contextmanager
    def transaction(self):
        if self._in_transaction:
            raise RuntimeError("Nested store transactions are unsupported")
        self._in_transaction = True
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        finally:
            self._in_transaction = False

    def _commit(self) -> None:
        if not self._in_transaction:
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def processing_config(self, document_id: str) -> str | None:
        row = self.connection.execute("SELECT config FROM processing_config WHERE document_id=?", (document_id,)).fetchone()
        return row[0] if row else None

    def save_config(self, document_id: str, config: str) -> None:
        self.connection.execute("INSERT OR REPLACE INTO processing_config VALUES (?,?)", (document_id, config))
        self._commit()

    def save_run(self, run_id: str, filename: str, status: str, events: list[dict]) -> None:
        self.connection.execute("INSERT OR REPLACE INTO processing_runs VALUES (?,?,?,?)",
                                (run_id, filename, status, json.dumps(events)))
        self._commit()

    def runs(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM processing_runs ORDER BY rowid DESC LIMIT 20")]

    def document_by_hash(self, sha256: str) -> Document | None:
        row = self.connection.execute("SELECT * FROM documents WHERE sha256=?", (sha256,)).fetchone()
        return self._document(row) if row else None

    def document(self, document_id: str) -> Document | None:
        row = self.connection.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        return self._document(row) if row else None

    def save_document(self, doc: Document) -> None:
        self.connection.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?)", (doc.id, doc.filename, doc.sha256, doc.page_count, doc.status, json.dumps(doc.warnings), doc.created_at.isoformat()))
        self._commit()

    def save_evidence(self, item: Evidence) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO evidence (id, document_id, page_index, printed_page, text, heading, bbox, tables) VALUES (?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.document_id,
                item.page_index,
                item.printed_page,
                item.text,
                item.heading,
                json.dumps(item.bbox),
                json.dumps([table.model_dump(mode="json") for table in item.tables]),
            ),
        )
        self._commit()

    def save_fact(self, item: Fact) -> None:
        self.connection.execute("INSERT OR REPLACE INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (item.id, item.document_id, item.evidence_id, item.subject, item.predicate, item.original_text, item.value_text, item.value_number, item.unit, item.period, item.scope, item.status, json.dumps(item.attributes)))
        self._commit()

    def save_relationship(self, item: Relationship) -> None:
        self.connection.execute("INSERT OR REPLACE INTO relationships VALUES (?,?,?,?,?,?,?)", (item.id, item.left_fact_id, item.right_fact_id, item.kind.value, item.confidence, item.explanation, item.created_at.isoformat()))
        self._commit()

    def clear_relationships(self) -> None:
        self.connection.execute("DELETE FROM relationships")
        self._commit()

    def save_issue(self, item: ProcessingIssue) -> None:
        self.connection.execute("INSERT OR REPLACE INTO issues VALUES (?,?,?,?,?,?,?)", (item.id, item.document_id, item.page_index, item.code, item.message, int(item.recoverable), item.created_at.isoformat()))
        self._commit()

    def issues(self, document_id: str) -> list[ProcessingIssue]:
        rows = self.connection.execute("SELECT * FROM issues WHERE document_id=? ORDER BY rowid DESC", (document_id,))
        return [ProcessingIssue(id=r["id"], document_id=r["document_id"], page_index=r["page_index"], code=r["code"], message=r["message"], recoverable=bool(r["recoverable"]), created_at=r["created_at"]) for r in rows]

    def delete_document(self, document_id: str) -> None:
        fact_ids = [r[0] for r in self.connection.execute("SELECT id FROM facts WHERE document_id=?", (document_id,))]
        if fact_ids:
            placeholders = ",".join("?" for _ in fact_ids)
            self.connection.execute(f"DELETE FROM relationships WHERE left_fact_id IN ({placeholders}) OR right_fact_id IN ({placeholders})", tuple(fact_ids * 2))
        self.connection.execute("DELETE FROM facts WHERE document_id=?", (document_id,))
        self.connection.execute("DELETE FROM evidence WHERE document_id=?", (document_id,))
        self.connection.execute("DELETE FROM issues WHERE document_id=?", (document_id,))
        self.connection.execute("DELETE FROM documents WHERE id=?", (document_id,))
        self._commit()

    def documents(self) -> list[Document]:
        return [self._document(r) for r in self.connection.execute("SELECT * FROM documents ORDER BY created_at DESC")]

    def evidence(self, evidence_id: str) -> Evidence | None:
        row = self.connection.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        if not row:
            return None
        bbox = json.loads(row["bbox"]) if row["bbox"] else None
        tables = json.loads(row["tables"]) if "tables" in row.keys() and row["tables"] else []
        return Evidence(
            id=row["id"],
            document_id=row["document_id"],
            page_index=row["page_index"],
            printed_page=row["printed_page"],
            text=row["text"],
            heading=row["heading"],
            bbox=tuple(bbox) if bbox else None,
            tables=tables,
        )

    def evidence_count(self, document_id: str) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM evidence WHERE document_id=?", (document_id,)).fetchone()
        return int(row["count"])

    def document_stats(self, document_id: str) -> dict[str, int]:
        rows = self.connection.execute("SELECT attributes FROM facts WHERE document_id=?", (document_id,)).fetchall()
        model_facts = sum(json.loads(row["attributes"]).get("extractor") == "ollama" for row in rows)
        tables = self.connection.execute("SELECT tables FROM evidence WHERE document_id=?", (document_id,)).fetchall()
        return {"facts": len(rows), "model_facts": model_facts,
                "text_pages": len(tables), "tables": sum(len(json.loads(row["tables"])) for row in tables)}

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def facts(self, query: str = "", limit: int | None = None, document_id: str | None = None) -> list[Fact]:
        sql = "SELECT * FROM facts WHERE (subject LIKE ? OR predicate LIKE ? OR original_text LIKE ?)"
        params: list[object] = [f"%{query}%"] * 3
        if document_id:
            sql += " AND document_id=?"
            params.append(document_id)
        sql += " ORDER BY rowid DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.connection.execute(sql, tuple(params))
        return [self._fact(row) for row in rows]

    def facts_by_ids(self, fact_ids: list[str]) -> list[Fact]:
        if not fact_ids:
            return []
        unique_ids = list(dict.fromkeys(fact_ids))
        placeholders = ",".join("?" for _ in unique_ids)
        rows = self.connection.execute(f"SELECT * FROM facts WHERE id IN ({placeholders})", tuple(unique_ids))
        return [self._fact(row) for row in rows]

    def fact_count(self, query: str = "", document_id: str | None = None) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM facts WHERE (subject LIKE ? OR predicate LIKE ? OR original_text LIKE ?) AND (? IS NULL OR document_id=?)",
            tuple([f"%{query}%"] * 3 + [document_id, document_id]),
        ).fetchone()
        return int(row["count"])

    def relationships(self) -> list[Relationship]:
        return [Relationship(id=r["id"], left_fact_id=r["left_fact_id"], right_fact_id=r["right_fact_id"], kind=r["kind"], confidence=r["confidence"], explanation=r["explanation"], created_at=r["created_at"]) for r in self.connection.execute("SELECT * FROM relationships ORDER BY confidence DESC")]

    @staticmethod
    def _document(row: sqlite3.Row) -> Document:
        return Document(id=row["id"], filename=row["filename"], sha256=row["sha256"], page_count=row["page_count"], status=row["status"], warnings=json.loads(row["warnings"]), created_at=row["created_at"])

    @staticmethod
    def _fact(row: sqlite3.Row) -> Fact:
        return Fact(
            id=row["id"],
            document_id=row["document_id"],
            evidence_id=row["evidence_id"],
            subject=row["subject"],
            predicate=row["predicate"],
            original_text=row["original_text"],
            value_text=row["value_text"],
            value_number=row["value_number"],
            unit=row["unit"],
            period=row["period"],
            scope=row["scope"],
            status=row["status"],
            attributes=json.loads(row["attributes"]),
        )
