"""Optional real-model selection checks. Require credentials and incur API usage."""

import json
import os
import sqlite3

import pytest
from agents import Runner, RunConfig
from agents.models.openai_provider import OpenAIProvider
from openai import AsyncOpenAI

from reading_list.agent import build_agent
from reading_list.connection import connect_server

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_AGENT") != "1" or not os.getenv("OPENAI_API_KEY"),
        reason="Requires RUN_LIVE_AGENT=1 and OPENAI_API_KEY; incurs API usage",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt,expected,arguments,status,already_saved", [
    ("Find the book Deep Learning. Don't save it.", "search_catalog", {"query": "Deep Learning"}, "ok", False),
    ("Add book B001 to my reading list.", "save_to_reading_list", {"book_id": "B001"}, "saved", False),
    ("Add book B001 again.", "save_to_reading_list", {"book_id": "B001"}, "already_saved", True),
    ("Find and save Introduction to Algorithms.", "find_and_save_book", {"query": "Introduction to Algorithms"}, "saved", False),
    ("Find and save a book about machine learning.", "find_and_save_book", {"query": "machine learning"}, "ambiguous", False),
    ("Add book B999 to my reading list.", "save_to_reading_list", {"book_id": "B999"}, "invalid_id", False),
    ("Find the book Quantum Banana.", "search_catalog", {"query": "Quantum Banana"}, "no_matches", False),
])
async def test_live_agent_routing(tmp_path, prompt, expected, arguments, status, already_saved):
    path = tmp_path / "live.sqlite3"
    # Each case owns its API client and closes it within that case's event loop.
    async with AsyncOpenAI() as client, connect_server(path) as server:
        if already_saved:
            await server.call_tool("save_to_reading_list", {"book_id": "B001"})
        result = await Runner.run(
            build_agent(server), prompt, max_turns=5,
            run_config=RunConfig(tracing_disabled=True, model_provider=OpenAIProvider(openai_client=client)),
        )
        calls = [item.raw_item for item in result.new_items if item.type == "tool_call_item"]
        assert [(call.name, json.loads(call.arguments)) for call in calls] == [(expected, arguments)]
        outputs = [item.output for item in result.new_items if item.type == "tool_call_output_item"]
        assert json.loads(outputs[0])["status"] == status
    if status in {"saved", "already_saved"}:
        with sqlite3.connect(path) as db:
            expected_id = "B004" if expected == "find_and_save_book" else "B001"
            assert db.execute("SELECT book_id FROM reading_list").fetchall() == [(expected_id,)]
    else:
        assert not path.exists()
