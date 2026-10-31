# MCP reading and server exploration

The Hugging Face article introduces MCP as a way to connect AI applications to
external data and tools without building a separate integration for every
service [1]. The linked full article explains how applications discover server
capabilities, including tools, resources, and prompts [2]. What matters for this
assignment is that MCP supports actions as well as lookups: an agent can retrieve
information and use another tool to change something outside the model.

MCP has three main roles. The Host manages the model and the user's interaction.
An MCP Client inside the Host connects to a Server, which provides the tools.
For my reading list assistant, the Python application using the Agents SDK is
the Host, `MCPServerStdio` provides the Client connection, and FastMCP runs the
Server. The client obtains tool descriptions and input schemas, sends tool
requests, and receives results. Here, those messages travel through the server
process's standard input and output. Logs go to standard error so they do not
interfere with the protocol [3].

I looked at the reference filesystem server's entry point, tool registrations,
shared helpers, and README [4-7]. The entry point resolves the allowed
directories before starting the stdio server. Tools have descriptions, argument
schemas, and annotations indicating behavior such as read-only access. The
separate `read_text_file` and `write_file` tools make their purposes clear.
Shared path validation also avoids having each tool implement its own access
checks.

Some interfaces are easier to predict than others. `read_text_file` can return
an entire file, its beginning, or its end. These options still serve one purpose,
and requesting both head and tail produces an explicit error. `edit_file` needs
more care because it supports several edits and a dry-run option. The deprecated
`read_file` alias also overlaps with `read_text_file`, giving the agent another
name for essentially the same operation [5].

Overall, I found the server's separation of operations and shared validation
useful examples of the class principles. However, directory restrictions alone
cannot determine whether a write matches the user's intent. In my toolkit,
searching never saves anything, and the combined tool refuses to save when
several books match. That keeps the effect of each request easier to explain
and check.

## Sources


1. [Ksenia Se, Hugging Face MCP article](https://huggingface.co/blog/Kseniase/mcp).
2. [Linked full article, Turing Post](https://www.turingpost.com/p/mcp).
3. [OpenAI Agents SDK MCP documentation](https://openai.github.io/openai-agents-python/mcp/).
4. [Filesystem entry point](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/index.ts).
5. [Filesystem tool registration](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/server.ts).
6. [Filesystem shared helpers](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/lib.ts).
7. [Filesystem README](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/README.md).
