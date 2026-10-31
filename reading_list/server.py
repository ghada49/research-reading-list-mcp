"""FastMCP stdio entry point; stdout belongs exclusively to MCP."""

import logging
import os
from pathlib import Path

# Disable library startup network checks even when run directly.
os.environ.setdefault("FASTMCP_CHECK_FOR_UPDATES", "off")

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from reading_list.models import FindSaveResult, SaveResult, SearchResult
from reading_list.service import ReadingList

ROOT = Path(__file__).resolve().parent.parent
library = ReadingList(Path(os.environ.get("READING_LIST_DB", ROOT / "data" / "reading_list.sqlite3")))
mcp = FastMCP("Research Reading List - Seeded Demo", strict_input_validation=True)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False))
def search_catalog(query: str) -> SearchResult:
    """DATA: Search seeded demo books by title, author, ID, or description (all words must match). Read-only. Returns status, message, books [{id,title,authors,description}]. Blank or >500-character queries return invalid_input; absent books return no_matches."""
    return SearchResult.model_validate(library.search_catalog(query))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def save_to_reading_list(book_id: str) -> SaveResult:
    """ACTION: Persist one known exact catalog ID (such as B001) in SQLite. Call only when the user requests saving. Returns status, message, and book when known. Status is saved, already_saved (no duplicate), invalid_id, or storage_error."""
    return SaveResult.model_validate(library.save_to_reading_list(book_id))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def find_and_save_book(query: str) -> FindSaveResult:
    """ORCHESTRATION: For an explicit find-and-save request, search then save through shared Data and Action logic. Save only a unique normalized title or a sole match. Return status, message, book or candidate books, and ordered steps. Ambiguous, no_matches, and invalid_input never save; duplicates return already_saved."""
    return FindSaveResult.model_validate(library.find_and_save_book(query))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mcp.run(transport="stdio", show_banner=False)
