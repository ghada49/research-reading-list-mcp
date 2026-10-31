import json
import sqlite3

import pytest

from reading_list.connection import connect_server


def payload(result):
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(next(block.text for block in result.content if block.type == "text"))


@pytest.mark.asyncio
async def test_real_mcp_roundtrip_and_restart(tmp_path):
    path = tmp_path / "mcp.sqlite3"
    async with connect_server(path) as server:
        tools = await server.list_tools()
        assert {tool.name for tool in tools} == {"search_catalog", "save_to_reading_list", "find_and_save_book"}
        assert len(tools) == 3
        for tool in tools:
            assert tool.description
            assert tool.input_schema["type"] == "object"
            assert {"status", "message"} <= tool.output_schema["properties"].keys()
            assert tool.annotations.idempotent_hint is True
            assert tool.annotations.read_only_hint is (tool.name == "search_catalog")
        search_schema = next(tool.output_schema for tool in tools if tool.name == "search_catalog")
        assert set(search_schema["properties"]["status"]["enum"]) == {"ok", "no_matches", "invalid_input"}
        assert payload(await server.call_tool("search_catalog", {"query": "Deep Learning"}))["status"] == "ok"
        assert not path.exists()
        assert payload(await server.call_tool("save_to_reading_list", {"book_id": "B999"}))["status"] == "invalid_id"
        assert payload(await server.call_tool("search_catalog", {"query": "zzzzunknown"}))["status"] == "no_matches"
        assert payload(await server.call_tool("find_and_save_book", {"query": "machine learning"}))["status"] == "ambiguous"
        assert not path.exists()
        saved = payload(await server.call_tool("find_and_save_book", {"query": "Deep Learning"}))
        assert saved["status"] == "saved"
        assert [step["tool"] for step in saved["steps"]] == ["search_catalog", "save_to_reading_list"]
        before = path.read_bytes()
        assert payload(await server.call_tool("search_catalog", {"query": "Deep Learning"}))["books"][0]["id"] == "B001"
        assert payload(await server.call_tool("search_catalog", {"query": "Quantum Banana"}))["status"] == "no_matches"
        assert payload(await server.call_tool("find_and_save_book", {"query": "machine learning"}))["status"] == "ambiguous"
        assert path.read_bytes() == before
    async with connect_server(path) as restarted:
        assert payload(await restarted.call_tool("save_to_reading_list", {"book_id": "B001"}))["status"] == "already_saved"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM reading_list").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_trace_precedes_dispatch_forwards_meta_and_redacts_key(tmp_path, capsys, monkeypatch):
    from agents.mcp import MCPServerStdio

    secret = "sk-offline-redaction-test-not-a-real-key"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    original = MCPServerStdio.call_tool

    async def inspect_dispatch(self, tool_name, arguments, meta=None):
        # Inspect before the real client sends anything; do not fake its response.
        before = capsys.readouterr().out
        assert "Client -> Server: search_catalog" in before
        assert "[REDACTED]" in before and secret not in before
        assert "Server -> Client:" not in before
        assert arguments == {"query": secret}  # Redaction changes display only.
        assert meta == {"test_label": "forwarded"}
        return await original(self, tool_name, arguments, meta=meta)

    monkeypatch.setattr(MCPServerStdio, "call_tool", inspect_dispatch)
    async with connect_server(tmp_path / "trace.sqlite3", visible=True) as server:
        result = await server.call_tool("search_catalog", {"query": secret}, meta={"test_label": "forwarded"})
        assert payload(result)["status"] == "no_matches"
        after = capsys.readouterr().out
        assert "Server -> Client: search_catalog" in after
        assert '"status": "no_matches"' in after
        assert secret not in after


@pytest.mark.asyncio
async def test_malformed_mcp_arguments_return_error_without_write(tmp_path, capsys):
    path = tmp_path / "malformed.sqlite3"
    async with connect_server(path, visible=True) as server:
        result = await server.call_tool("search_catalog", {"query": 123})
        assert result.is_error
        assert "Server -> Client: search_catalog" in capsys.readouterr().out
    assert not path.exists()
