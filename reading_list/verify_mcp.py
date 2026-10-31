"""Offline demonstration using real MCP subprocesses, without a model call."""

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

from reading_list.connection import ROOT, connect_server


def unpack(result) -> dict:
    if result.is_error:
        raise RuntimeError(f"MCP protocol/tool error: {result.content}")
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(next(block.text for block in result.content if block.type == "text"))


async def demonstrate(path: Path) -> None:
    print("OFFLINE MCP verification: real client/server; no LLM or API usage.")
    print("Database:", path.resolve())
    async with connect_server(path) as server:
        tools = await server.list_tools()
        names = [tool.name for tool in tools]
        assert len(names) == 3 and set(names) == {"search_catalog", "save_to_reading_list", "find_and_save_book"}
        print("Discovered:", ", ".join(names))
        requests = [
            ("search_catalog", {"query": "Deep Learning"}, {"ok"}),
            ("search_catalog", {"query": "zzzzunknown"}, {"no_matches"}),
            ("save_to_reading_list", {"book_id": "B999"}, {"invalid_id"}),
            ("save_to_reading_list", {"book_id": "B002"}, {"saved", "already_saved"}),
            ("find_and_save_book", {"query": "machine learning"}, {"ambiguous"}),
            ("find_and_save_book", {"query": "Deep Learning"}, {"saved", "already_saved"}),
        ]
        for name, arguments, statuses in requests:
            print(f"Client -> server: {name} {arguments}")
            result = unpack(await server.call_tool(name, arguments))
            print("Server -> client:", json.dumps(result, indent=2))
            assert result["status"] in statuses
    async with connect_server(path) as restarted:
        result = unpack(await restarted.call_tool("save_to_reading_list", {"book_id": "B001"}))
        assert result["status"] == "already_saved"
        print("After server restart:", json.dumps(result))
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT book_id, title, saved_at FROM reading_list ORDER BY book_id").fetchall()
    assert {"B001", "B002"} <= {row[0] for row in rows}
    print("Persistent SQLite rows:", json.dumps(rows, indent=2))
    print("MCP verification passed. Live model routing is a separate check.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "offline_demo.sqlite3")
    asyncio.run(demonstrate(parser.parse_args().db))
