import sqlite3

import pytest

from reading_list.service import ReadingList


@pytest.fixture
def library(tmp_path):
    return ReadingList(tmp_path / "reading.sqlite3")


def test_search_is_read_only(library):
    result = library.search_catalog("deep learning")
    assert result["status"] == "ok"
    assert result["books"][0]["id"] == "B001"
    assert {"id", "title", "authors", "description"} <= result["books"][0].keys()
    assert not library.db_path.exists()


@pytest.mark.parametrize("query,status", [("zzzzunknown", "no_matches"), ("  ", "invalid_input"), ("x" * 501, "invalid_input")])
def test_search_failures(library, query, status):
    assert library.search_catalog(query)["status"] == status


def test_save_persists_and_prevents_duplicates(library):
    assert library.save_to_reading_list("B001")["status"] == "saved"
    assert ReadingList(library.db_path).save_to_reading_list("B001")["status"] == "already_saved"
    with sqlite3.connect(library.db_path) as db:
        assert db.execute("SELECT book_id FROM reading_list").fetchall() == [("B001",)]


@pytest.mark.parametrize("book_id", ["", "B999", "'; DROP TABLE reading_list;--"])
def test_invalid_identifier_does_not_write(library, book_id):
    assert library.save_to_reading_list(book_id)["status"] == "invalid_id"
    assert not library.db_path.exists()


def test_orchestration_sequence_and_duplicate(library):
    result = library.find_and_save_book("Deep Learning")
    assert result["status"] == "saved"
    assert [step["tool"] for step in result["steps"]] == ["search_catalog", "save_to_reading_list"]
    assert result["book"]["id"] == "B001"
    assert library.find_and_save_book("Deep Learning")["status"] == "already_saved"


@pytest.mark.parametrize("query,status", [("machine learning", "ambiguous"), ("zzzzunknown", "no_matches"), ("", "invalid_input")])
def test_orchestration_failure_never_saves(library, query, status):
    result = library.find_and_save_book(query)
    assert result["status"] == status
    assert len(result["steps"]) == 1
    assert not library.db_path.exists()


def test_storage_failure_is_predictable(tmp_path):
    library = ReadingList(tmp_path)  # A directory cannot be an SQLite file.
    assert library.save_to_reading_list("B001")["status"] == "storage_error"
    assert library.find_and_save_book("Deep Learning")["status"] == "storage_error"


def test_orchestration_reuses_shared_methods_in_order(library, monkeypatch):
    calls = []
    search = library.search_catalog
    save = library.save_to_reading_list

    def observed_search(query):
        calls.append(("search", query))
        return search(query)

    def observed_save(book_id):
        calls.append(("save", book_id))
        return save(book_id)

    monkeypatch.setattr(library, "search_catalog", observed_search)
    monkeypatch.setattr(library, "save_to_reading_list", observed_save)
    assert library.find_and_save_book("Deep Learning")["status"] == "saved"
    assert calls == [("search", "Deep Learning"), ("save", "B001")]
    calls.clear()
    assert library.find_and_save_book("machine learning")["status"] == "ambiguous"
    assert calls == [("search", "machine learning")]
