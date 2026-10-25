# Adding MCP servers

MCP servers give the assistant extra tools (GitHub, Gmail, databases, …). You add them per user in **Settings (⚙︎) → MCP servers → + Add server**.

## The form

- **Name**: letters, digits, `_` and `-`. You can leave it empty if the JSON already names the server.
- **JSON**: paste the config from the server's docs. Any of these shapes works:
  - a single entry: `{ "command": … }` or `{ "url": … }`
  - a named entry: `{ "github": { … } }`
  - the full block: `{ "mcpServers": { … } }`, or `{ "servers": { … } }` (VS Code)

Add one server at a time.

## Local server (runs a command)

```json
{
  "command": "uvx",
  "args": ["mcp-server-git"],
  "env": { "SOME_TOKEN": "..." }
}
```

`command` is the program to run. Put every argument in `args`, as a separate string. The program (`npx`, `uvx`, `docker`, …) must be installed on this machine.

## Remote server (URL)

```json
{
  "url": "https://example.com/mcp",
  "headers": { "Authorization": "Bearer ..." }
}
```

Only streamable HTTP is supported. SSE servers (`"type": "sse"`) are not.

## Tokens and secrets

- Values in `env` and `headers` are stored **encrypted**. `command`, `args` and `url` are stored as plain text, so never put a token there.
- Sign-in through the browser (OAuth) is not supported. Use a personal access token / API key in `headers` or `env` instead.
- Docs written for VS Code use placeholders like `${input:github_mcp_pat}` plus an `"inputs"` block. This app doesn't fill those in. Replace the placeholder with the real value and delete `"inputs"`. The same goes for `${env:…}` and `${workspaceFolder}`.

## Example: GitHub

1. Create a token at <https://github.com/settings/tokens/new> with the `repo` scope.
2. Add the server:

```json
{
  "mcpServers": {
    "github": {
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer ghp_your_token" }
    }
  }
}
```

This server works with GitHub through its API: repositories, branches, files, issues, pull requests. It does **not** push your local commits. That still takes `git push` in a terminal.

## After adding

The app connects to the server right away and lists its tools. The server's row then shows its status:

| Status | Meaning |
|---|---|
| `Connected · N tool(s)` | Ready. |
| `Unavailable (http_401)` | The token is missing or wrong. |
| `Unavailable (spawn_failed)` | The command could not be started. Check that it is installed. |
| `Unavailable (timeout)` | The server didn't answer in time. |

A server that fails the check is turned off.
- If the problem was outside the config (Docker wasn't running, no network), fix it and press **Check**. A passing check turns the server back on.
- To change the config, delete the server and add it again. Servers can't be edited yet.

- **Tools**: lists the server's tools. Tools of a server you added **ask for confirmation in the chat** every time. Tick a tool in the *Run without asking* column only if you trust it to run on its own.
- **Enabled / Disabled**: turns the server on or off.
- **✕**: deletes the server and its stored secrets.

## Not supported

- More than one server in one paste
- Keys such as `cwd`, `timeout`, `envFile`, `disabled`, `autoApprove`. The form rejects them.
- Comments (`//`) inside the JSON
- Tools that aren't MCP servers. For example, the MCP Inspector prints plain text instead of the MCP protocol.
