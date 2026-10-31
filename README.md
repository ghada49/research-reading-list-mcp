# Research Reading List Assistant

EECE 503P/798S - C5 Agent Tools. A small Python assistant searches an explicitly
**seeded demonstration catalog** of eight academic books and saves selected
books to a persistent local reading list. Descriptions are short demo summaries,
not publisher-provided metadata. No external catalog API is needed.

## Architecture

```text
User prompt -> OpenAI Agents SDK host -> model chooses discovered MCP tool
            -> MCPServerStdio client -> FastMCP subprocess -> shared service
            <- tool result          <- stdio response    <- catalog / SQLite
            -> model's final answer
```

The host imports no service implementation. It supplies `mcp_servers=[server]`
to the agent, so SDK tool discovery and execution use a real MCP connection.
The model request uses OpenAI's API; the local MCP transport uses stdin/stdout.
Server logging goes to stderr. SDK cloud tracing is disabled. The host uses
`VisibleMCPServer`, a small `MCPServerStdio` subclass, to show discovered tools,
print each request immediately before the SDK sends it, and print the received
result immediately after it returns. All trace lines are flushed to the terminal
before the final assistant response. Repeated cached discovery is not printed
as new network traffic. Request metadata and environment variables are not
displayed; the configured API key is redacted if it appears in a payload.

| Category | Tool | Responsibility and predictable outcomes |
|---|---|---|
| Data | `search_catalog(query: str)` | Read-only lookup; `ok`, `no_matches`, `invalid_input` |
| Action | `save_to_reading_list(book_id: str)` | Commit one known book; `saved`, `already_saved`, `invalid_id`, `storage_error` |
| Orchestration | `find_and_save_book(query: str)` | Reuse search then save; adds `ambiguous` and ordered `steps` |

Exactly three MCP tools are registered. No resources or additional tools are
exposed. Resources are optional in the PDF; search is a callable Data tool.
Outputs are validated Pydantic models, advertised as explicit JSON schemas and
documented in each tool's description: `status` and
`message` always exist; searches include `books`; valid saves include `book`;
orchestration includes `steps` and either `book` or candidate `books`.
Each book has `id`, `title`, `authors`, and `description`.
Optional fields can be null; unused candidate lists are empty. Status values are
enumerated in the schemas. The Data tool advertises `readOnlyHint=true`. Both
writing tools advertise `readOnlyHint=false` and `destructiveHint=false`. All
three advertise `idempotentHint=true`: repeating them adds no further side effect,
although a repeated save returns `already_saved` instead of `saved`. These are
advisory hints, not permissions or enforcement mechanisms.
Domain failures use status values; malformed MCP arguments produce protocol tool
errors. Callers must inspect status instead of treating every response as success.

Search normalizes case and punctuation and requires all query words to occur
somewhere in a book's fields. It rejects blank or >500-character queries.
Orchestration prefers a unique normalized exact title; otherwise it requires a
single result. Several candidates produce `ambiguous` without a write. Exact IDs
are case-sensitive for saving (for example `B001`).

Tool selection belongs to the model. The host has no prompt keyword dispatcher.
Its instructions require catalog evidence, forbid writes for lookup-only
requests, and tell the model to extract a title or topic from conversational
wording (for example, `machine learning` from "a book about machine learning").
Ambiguity must be shown to the user, never bypassed by choosing the first book.
Orchestration's `steps` are shared Python service calls inside one MCP request;
they are not additional Client -> Server messages.

## Installation (PowerShell, project root)

Prerequisites: Python 3.11 or later (verified on Windows with Python 3.13.5),
internet for package installation, and an OpenAI API key with model access for
the live agent. Offline tests and the MCP verification do not need a key.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Activation is unnecessary. If virtual-environment creation reports an ensurepip
error, use a working global pip to bootstrap packages into that environment:

```powershell
python -m pip --python .\.venv\Scripts\python.exe install -r requirements.txt
```

Direct dependency versions are pinned in `requirements.txt`. Upgrading
dependencies requires rerunning the integration tests because both SDKs evolve.

## Configuration and running

Set credentials only in your terminal's environment. `.env.example` documents
the names; the application does not automatically load `.env` files.

```powershell
$secureKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
$env:OPENAI_MODEL = 'gpt-4.1-mini'
.\.venv\Scripts\python -m reading_list.agent "Search the catalog for Deep Learning. Do not save anything."
.\.venv\Scripts\python -m reading_list.agent "Save book B002 to my reading list."
.\.venv\Scripts\python -m reading_list.agent "Find and save Introduction to Algorithms."
.\.venv\Scripts\python -m reading_list.agent "Find and save a book about machine learning."
```

The agent starts and closes its server automatically. Run the server manually
only when connecting a separate MCP client:

```powershell
.\.venv\Scripts\python -m reading_list.server
```

It waits for MCP protocol messages, not natural-language terminal input. Stop
with Ctrl+C. If a live agent fails, check model access, account quota, network,
credentials, and server stderr. `OPENAI_MODEL` may name another accessible model.
No paid API calls were made automatically as part of setup.

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m reading_list.verify_mcp
```

The first command runs service, subprocess MCP, and scripted Agent/Runner tests.
Seven live routing cases in `tests/test_live_agent.py` are skipped unless
explicitly enabled. The second prints real discovery,
tool requests, responses, and SQLite rows, then restarts the server and checks
duplicate prevention. It is an **offline MCP demonstration**, not a live AI run.
It uses `data/offline_demo.sqlite3` and safely supports repeated runs.

`tests/test_agent_integration.py` replaces only the model with a scripted SDK
`Model`. It still uses the actual Agent, Runner, MCP client, subprocess server,
and SQLite. It checks exact arguments, real returned statuses, immediate traces,
and stored rows. Scripted decisions verify integration; they do not prove that a
real language model interprets the request correctly. The separate live tests
check that interpretation with natural-language prompts and no tool names.

Optional paid live routing verification (requires configured key and network):

```powershell
$env:RUN_LIVE_AGENT = '1'
.\.venv\Scripts\python -m pytest tests/test_live_agent.py -v
Remove-Item Env:RUN_LIVE_AGENT
```

In Git Bash, with your key already exported:

```bash
RUN_LIVE_AGENT=1 ./.venv/Scripts/python.exe -m pytest tests/test_live_agent.py -v
```

## Persistence

The agent's default file is `data/reading_list.sqlite3`, anchored to the project
directory. Override with `$env:READING_LIST_DB = 'C:\absolute\path\demo.sqlite3'`.
The database is created on the first valid save, with columns `book_id` (primary
key), `title`, and UTC `saved_at`. Transactions commit before success is returned.
SQLite enforces uniqueness, including concurrent duplicate insertions. Search
does not touch the database. The seed file is never changed by any tool.

Inspect saved rows without registering an extra MCP tool:

```powershell
.\.venv\Scripts\python -c "import sqlite3; print(sqlite3.connect('data/reading_list.sqlite3').execute('SELECT book_id,title,saved_at FROM reading_list').fetchall())"
```

For a fresh recording, choose a new database filename instead of deleting your
existing list. Test files use isolated temporary databases in `.test-tmp`.
Database files, credentials, environments, and caches are excluded by `.gitignore`.

## Deliverables and limitations

- `SUMMARY.md`: 300-400-word researched article/server critique and source links.
- `REFLECTION.md`: two paragraphs about tool boundaries and practical tradeoffs.

The catalog is small, fixed, and has no semantic ranking. The list has one local
user, with no view/delete MCP tool, authentication, or migration machinery.
SQLite stores IDs and titles, not a full catalog copy. Model routing depends on
the selected model and is only verified by an enabled live test. The reflection should be reviewed in your
own voice before submission. You must record the video and provide real
repository/video links; this project does not fabricate those deliverables.

Implementation references: [FastMCP tools](https://gofastmcp.com/servers/tools)
and [Agents SDK MCP integration](https://openai.github.io/openai-agents-python/mcp/).
