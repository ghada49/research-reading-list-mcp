"""Output contracts advertised and validated by FastMCP."""

from typing import Literal

from pydantic import BaseModel, Field


class Book(BaseModel):
    id: str
    title: str
    authors: list[str]
    description: str


class SearchResult(BaseModel):
    status: Literal["ok", "no_matches", "invalid_input"]
    message: str
    books: list[Book]


class SaveResult(BaseModel):
    status: Literal["saved", "already_saved", "invalid_id", "storage_error"]
    message: str
    book: Book | None = None


class Step(BaseModel):
    tool: Literal["search_catalog", "save_to_reading_list"]
    status: Literal["ok", "no_matches", "invalid_input", "saved", "already_saved", "invalid_id", "storage_error"]
    match_count: int | None = Field(default=None, ge=0)
    book_id: str | None = None


class FindSaveResult(BaseModel):
    status: Literal["saved", "already_saved", "invalid_id", "storage_error", "ambiguous", "no_matches", "invalid_input"]
    message: str
    book: Book | None = None
    books: list[Book] = Field(default_factory=list)
    steps: list[Step] = Field(description="Ordered shared service operations, not additional MCP requests.")
