"""Scripted model decisions, real Agents Runner and real MCP subprocesses.

These tests verify SDK/MCP plumbing and effects, not natural-language reasoning.
Only the model is scripted; tool responses always come from the actual server.
"""

import json
import sqlite3

import pytest
from agents import Model, Runner, RunConfig
from agents.items import ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from reading_list.agent import build_agent
from reading_list.connection import connect_server


class ScriptedModel(Model):
    def __init__(self, requests, check_before_final=None):
        self.requests = requests
        self.calls = 0
        self.results = []
        self.check_before_final = check_before_final

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs):
        assert {tool.name for tool in tools} == {
            "search_catalog", "save_to_reading_list", "find_and_save_book",
        }
        if self.calls:
            outputs = [item for item in input if isinstance(item, dict)
                       and item.get("type") == "function_call_output"]
            assert outputs[-1]["call_id"] == f"call_{self.calls}"
            result = json.loads(outputs[-1]["output"])
            assert result["status"] == self.requests[self.calls - 1][2]
            self.results.append(result)
        if self.calls < len(self.requests):
            name, arguments, _ = self.requests[self.calls]
            self.calls += 1
            output = [ResponseFunctionToolCall(
                type="function_call", id=f"fc_{self.calls}", call_id=f"call_{self.calls}",
                name=name, arguments=json.dumps(arguments),
            )]
        else:
            if self.check_before_final:
                self.check_before_final()
            output = [ResponseOutputMessage(
                type="message", id="final", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", text="Scripted test complete.", annotations=[])],
            )]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError("This test exercises Runner.run, not model streaming.")
        yield  # Make this an async iterator as required by the SDK Model interface.


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt,name,arguments,status", [
    ("Find the book Deep Learning. Don't save it.", "search_catalog", {"query": "Deep Learning"}, "ok"),
    ("Add book B001 to my reading list.", "save_to_reading_list", {"book_id": "B001"}, "saved"),
    ("Find and save Introduction to Algorithms.", "find_and_save_book", {"query": "Introduction to Algorithms"}, "saved"),
    ("Find and save a book about machine learning.", "find_and_save_book", {"query": "machine learning"}, "ambiguous"),
    ("Add book B999 to my reading list.", "save_to_reading_list", {"book_id": "B999"}, "invalid_id"),
    ("Find the book Quantum Banana.", "search_catalog", {"query": "Quantum Banana"}, "no_matches"),
])
async def test_runner_uses_real_mcp_and_receives_evidence(tmp_path, capsys, prompt, name, arguments, status):
    path = tmp_path / "runner.sqlite3"

    def check_before_final():
        # These must already be visible while the model has not yet finished.
        trace = capsys.readouterr().out
        assert "MCP discovered:" in trace
        assert f"Client -> Server: {name} " in trace
        assert f"Server -> Client: {name} " in trace
        assert json.dumps(arguments) in trace
        assert f'"status": "{status}"' in trace

    model = ScriptedModel([(name, arguments, status)], check_before_final)
    async with connect_server(path, visible=True) as server:
        result = await Runner.run(build_agent(server), prompt,
                                  run_config=RunConfig(model=model, tracing_disabled=True))
    assert result.final_output == "Scripted test complete."
    calls = [item.raw_item for item in result.new_items if item.type == "tool_call_item"]
    assert [(call.name, json.loads(call.arguments)) for call in calls] == [(name, arguments)]
    if status == "saved":
        with sqlite3.connect(path) as db:
            expected = "B004" if name == "find_and_save_book" else "B001"
            assert db.execute("SELECT book_id FROM reading_list").fetchall() == [(expected,)]
    else:
        assert not path.exists()
    if status == "ambiguous":
        assert {book["id"] for book in model.results[0]["books"]} == {"B001", "B002", "B007"}
        assert [step["tool"] for step in model.results[0]["steps"]] == ["search_catalog"]


@pytest.mark.asyncio
async def test_runner_duplicate_then_read_only_search_after_restart(tmp_path):
    path = tmp_path / "restart.sqlite3"
    async with connect_server(path) as server:
        await Runner.run(build_agent(server), "Add book B001.", run_config=RunConfig(
            model=ScriptedModel([("save_to_reading_list", {"book_id": "B001"}, "saved")]),
            tracing_disabled=True,
        ))
    before = path.read_bytes()
    model = ScriptedModel([
        ("save_to_reading_list", {"book_id": "B001"}, "already_saved"),
        ("search_catalog", {"query": "Deep Learning"}, "ok"),
        ("search_catalog", {"query": "Quantum Banana"}, "no_matches"),
    ])
    async with connect_server(path) as server:
        await Runner.run(build_agent(server), "Add B001 again, then find Deep Learning and Quantum Banana without saving.",
                         run_config=RunConfig(model=model, tracing_disabled=True))
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT book_id FROM reading_list").fetchall() == [("B001",)]
