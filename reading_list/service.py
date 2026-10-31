"""Shared tool logic. Catalog metadata and descriptions are seeded demo data."""

import json
import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def normalize(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


class ReadingList:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.catalog = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))

    def search_catalog(self, query: str) -> dict:
        """Return status, message, and books; never open or modify the database."""
        if not isinstance(query, str) or not normalize(query) or len(query) > 500:
            return {"status": "invalid_input", "message": "Provide a nonblank query of at most 500 characters.", "books": []}
        terms = normalize(query).split()
        books = [book for book in self.catalog if all(
            term in normalize(" ".join([book["id"], book["title"], *book["authors"], book["description"]]))
            for term in terms
        )]
        return {"status": "ok" if books else "no_matches", "message": f"Found {len(books)} book(s) in the seeded demonstration catalog.", "books": books}

    def save_to_reading_list(self, book_id: str) -> dict:
        """Return saved/already_saved/invalid_id/storage_error, with book if known."""
        book = next((book for book in self.catalog if book["id"] == book_id), None)
        if book is None:
            return {"status": "invalid_id", "message": "Unknown book ID. Search the catalog for an exact ID first."}
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as db:
                db.execute("CREATE TABLE IF NOT EXISTS reading_list (book_id TEXT PRIMARY KEY, title TEXT NOT NULL, saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
                cursor = db.execute("INSERT OR IGNORE INTO reading_list (book_id, title) VALUES (?, ?)", (book_id, book["title"]))
                saved = cursor.rowcount == 1
        except (OSError, sqlite3.Error):
            logger.exception("Reading-list storage failed")
            return {"status": "storage_error", "message": "Could not save. Check the database path, permissions, and disk availability.", "book": book}
        return {"status": "saved" if saved else "already_saved", "message": "Book saved persistently." if saved else "Book is already in the reading list; no duplicate added.", "book": book}

    def find_and_save_book(self, query: str) -> dict:
        """Search then save only a unique normalized title or a sole result."""
        search = self.search_catalog(query)
        steps = [{"tool": "search_catalog", "status": search["status"], "match_count": len(search["books"])}]
        if search["status"] != "ok":
            return {**search, "steps": steps}
        exact = [book for book in search["books"] if normalize(book["title"]) == normalize(query)]
        candidates = exact or search["books"]
        if len(candidates) != 1:
            return {"status": "ambiguous", "message": "Several books match. Ask the user to choose a title or ID; nothing saved.", "books": candidates, "steps": steps}
        result = self.save_to_reading_list(candidates[0]["id"])
        steps.append({"tool": "save_to_reading_list", "status": result["status"], "book_id": candidates[0]["id"]})
        logger.info("Orchestration sequence: %s", steps)
        return {**result, "steps": steps}
