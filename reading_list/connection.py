"""Real Agents SDK MCP client connection; no service functions imported here."""

import os
import json
import sys
from pathlib import Path
from typing import Any

from agents.mcp import MCPServerStdio
from mcp.types import CallToolResult, Tool

ROOT = Path(__file__).resolve().parent.parent


class VisibleMCPServer(MCPServerStdio):
    """Print requests/results at the real SDK client boundary, before final output."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reported_tools: tuple[str, ...] | None = None

    def _print(self, text: str) -> None:
        # Never dump environment variables or request metadata. If a key is
        # accidentally included in a query/result, redact its literal value.
        secret = os.getenv("OPENAI_API_KEY")
        if secret:
            text = text.replace(secret, "[REDACTED]")
        print(text, flush=True)

    async def list_tools(self, run_context=None, agent=None) -> list[Tool]:
        tools = await super().list_tools(run_context=run_context, agent=agent)
        names = tuple(tool.name for tool in tools)
        if names != self._reported_tools:
            self._print("MCP discovered: " + ", ".join(names))
            self._reported_tools = names
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None,
                        meta: dict[str, Any] | None = None) -> CallToolResult:
        self._print(f"Client -> Server: {tool_name} {json.dumps(arguments)}")
        try:
            result = await super().call_tool(tool_name, arguments, meta=meta)
        except Exception as exc:
            self._print(f"MCP request failed: {tool_name} ({type(exc).__name__}; no result received)")
            raise
        if result.is_error:
            body = {"is_error": True, "content": [block.model_dump(mode="json") for block in result.content]}
        elif result.structured_content is not None:
            body = result.structured_content
        else:
            body = {"content": [block.model_dump(mode="json") for block in result.content]}
        self._print(f"Server -> Client: {tool_name} {json.dumps(body)}")
        return result


def connect_server(db_path: Path | None = None, *, visible: bool = False) -> MCPServerStdio:
    env = dict(os.environ)
    env["FASTMCP_CHECK_FOR_UPDATES"] = "off"
    if db_path is not None:
        env["READING_LIST_DB"] = str(Path(db_path).resolve())
    # The local server has no reason to receive the model provider credential.
    env.pop("OPENAI_API_KEY", None)
    server_type = VisibleMCPServer if visible else MCPServerStdio
    return server_type(
        name="Research reading list",
        params={"command": sys.executable, "args": ["-m", "reading_list.server"], "cwd": str(ROOT), "env": env},
        client_session_timeout_seconds=30,
        cache_tools_list=True,
        use_structured_content=True,
    )
