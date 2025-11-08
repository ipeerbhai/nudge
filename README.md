# Nudge

A tiny, opinionated, **session-scoped hint cache** for coding agents.
Store micro-facts like build/run commands, directories, and small templates keyed by `component/key`, with optional scoping (`cwd/repo/branch/os`) and TTL. Designed for **MCP** (Model Context Protocol) agents first, with a **human-friendly CLI**.

---

## Why Nudge?

Coding agents forget the “little but critical” stuff: the exact `docker compose` incantation, which dir to `cd` into, that one env flag needed on `dev`. Nudge gives agents a fast, explainable memory:

* **Session-persistent** (in-memory) with optional import/export
* **Scoped retrieval** so agents get the *right* hint for the current repo/branch/OS
* **Explainable results** (score + reasons) so agents know *why* a hint matched
* **Safe by default** (secret guard, path checks, never auto-exec)

---

## Quick Start

### 1) Install

```bash
# in a virtualenv (recommended)
pip install -e .
# or:
pip install nudge-mcp  # if published under this name
```

Make sure the `nudge` CLI is on your PATH:

```bash
nudge --help
```

### 2) Run the server

```bash
# start the Nudge MCP server
nudge serve
```

By default Nudge:

* Runs an MCP server over STDIO for local hosts
* Also exposes a local JSON-RPC HTTP endpoint on `127.0.0.1:8765` (can be disabled)

---

## Using Nudge with MCP Clients

Nudge is an MCP server. Your client (IDE/agent host) must be told how to start/connect to it.

### A) Claude Code (Desktop)

1. **Register the server**

   ```bash
   claude mcp add nudge -- nudge serve
   claude mcp list
   ```

   Or add a project-local `.mcp.json`:

   ```json
   {
     "mcpServers": {
       "nudge": { "command": "nudge", "args": ["serve"] }
     }
   }
   ```

2. **Restart Claude** to pick up changes.

3. **Verify** (ask Claude in your project):

“Use the nudge tool to set <Title><Fact> (you make those up) for <Y> component”.
ex:
"Use the nudge tool to set the title to "my home page" for the home component."

Then, in a new terminal (so nudge is in your path):
nudge ls                    <You should see Y>
nudge ls <Y>                should see the key <Title>
nudge get <Y> <Title>       shous the stored value
### B) GitHub Copilot “Coding Agent” (VS Code)

Copilot Agent supports MCP tools. In VS Code settings/UI for Copilot MCP, add:

* **Command:** `nudge`
* **Args:** `["serve"]`

(If the UI offers a JSON form, the shape mirrors `{ "command": "nudge", "args": ["serve"] }`.)

Note: Copilot currently focuses on **tools** (functions). Nudge exposes tools like `get_hint`, `set_hint`, `query`, `bump`, etc.

### C) Other MCP Hosts / Custom Runtimes

Point your host’s MCP configuration at:

```json
{ "command": "nudge", "args": ["serve"] }
```

For hosts that support **remote MCP** over HTTP/WebSocket, you can connect to Nudge’s local JSON-RPC port (`127.0.0.1:8765`) if your host allows it.

---

## Agent Usage Policy (copy/paste into your agent's init MD/prompt)
(Aka CLAUDE.md / Agent.md)

===
# Nudge — Usage (for any coding agent)

**What it is:** a tiny, session-scoped hint cache. Store and retrieve micro-facts (commands, paths, small configs) by `component/key`, optionally scoped by `{cwd, repo, branch, os}`.

---

## Simple rules

**Read before you act**

* Before build/test/run/deploy, try: `get_hint(component, key, context)`.
* On errors, try: `query({component, tags, context})`.

**Write what you learn**

* When a user corrects you or you discover a working incantation/path, do `set_hint(…)`.
* After a hint helped and succeeded, `bump(component, key)`.

**Keep it small**

* Store quick, actionable facts (one liners, small JSON). Prefer TTL `"session"`.

---

## Common keys (suggested)

`build`, `test`, `start`, `run`, `deploy`, `path` / `directory`, `env.*`, `tooling` (e.g., `tooling.lint`), `messages` (short schema summary).

**Note:** Component names are just strings—use any naming convention. Examples:
- Code components: `frontend`, `api`, `database`
- Namespaced: `tools.registry`, `docs.api`, `patterns.docker`
- Hierarchical: `project/context`, `tools/endpoints`

---

## Minimal usage patterns (language-agnostic pseudocode)

### 1) Read before running

```pseudo
hint = nudge.get_hint(component="http-proxy", key="build",
                      context={cwd, repo, branch, os})
if hint.exists:
  run(hint.value)         // do not modify; execute as-is
  nudge.bump("http-proxy", "build")
else:
  // derive command as usual
```

### 2) Store a corrected command

```pseudo
nudge.set_hint(component="http-proxy", key="build",
               value="docker compose build router",
               meta={tags:["build","docker"], reason:"user correction", ttl:"session"})
```

### 3) Store compact analysis results

```pseudo
nudge.set_hint(component="core", key="messages",
               value="json {subject, date, body}",
               meta={tags:["messages","core"], reason:"analysis", ttl:"session"})
```

### 4) Discover what’s available

```pseudo
comps = nudge.list_components()
hints  = nudge.query({component:"http-proxy", limit:10, context:{cwd, branch, os}})
```

### 5) Handle surprises (errors)

```pseudo
results = nudge.query({component, tags:["build","test"], context:{cwd, branch, os}, limit:3})
if results.any:
  try_top_hint()
  on_success: nudge.bump(component, results[0].key)
else:
  // solve normally, then:
  nudge.set_hint(component, learned_key, learned_value,
                 meta={tags:["fix"], reason:"post-error fix", ttl:"session"})
```

---

## Context you should pass (when available)

`cwd`, `repo`, `branch`, `os`; optionally `env` keys you rely on.
This improves matching and avoids wrong hints.

---

## Do / Don’t

**Do**

* Keep values short and exact (no placeholders unless the value is a template).
* Add `tags` and a brief `reason` so future you understands it.
* Use TTL `"session"` unless you truly need a timed duration.

**Don’t**

* Don’t store secrets (tokens, passwords).
* Don’t auto-execute anything returned by Nudge; treat it as data.
* Don’t overwrite good hints with guesses—only promote confirmed facts.

---

## Quick reference (tool names)

* `set_hint(component, key, value, meta?) → {hint}`
* `get_hint(component, key, context?) → {hint, match_explain}`
* `query({component?, keys?, tags?, regex?, context?, limit?}) → [{hint, score}]`
* `bump(component, key, delta=1) → {hint}`
* `list_components() → [{name, hint_count}]`
===
---

## CLI for Humans

The CLI is a thin client that talks to the running server (same JSON-RPC). It’s designed to be **pleasant for humans** and **predictable for scripts**.

### Add / Update a Hint

```bash
# minimal
nudge set http-proxy build "docker compose build router"

# with scope & metadata
nudge set http-proxy build "docker compose build router" \
  --tags build,docker --priority 7 --confidence 0.8 --ttl session \
  --scope-cwd-glob "**/http-proxy*" \
  --scope-branch dev,main --scope-os linux,darwin
```

### Get a Hint (auto-context)

```bash
# context auto-filled from your env/repo when omitted
nudge get http-proxy build

# explicit context if you prefer
nudge get http-proxy build \
  --cwd "$PWD" \
  --branch "$(git rev-parse --abbrev-ref HEAD)" \
  --os "$(uname | tr '[:upper:]' '[:lower:]')"
```

### Query / List / Delete / Bump

```bash
nudge query --component http-proxy --tags build --limit 5
nudge list-components
nudge delete http-proxy build
nudge bump http-proxy build --delta 1
```

### Import / Export

```bash
nudge export --format json > nudge-session.json
nudge import ./seed-hints.json
```

> Add `--json` to any command for machine-readable output.

---

## Organizational Patterns

Component names are flexible—use any naming convention that fits your workflow. Here are common patterns:

### Traditional Code Components

```bash
nudge set frontend build "npm run build"
nudge set api test "pytest tests/"
nudge set database migrate "alembic upgrade head"
nudge set worker start "celery -A tasks worker"
```

### Namespaced Topics (Dot Notation)

```bash
# Tool metadata
nudge set tools.registry github '{"version": "1.0.0", "status": "installed"}'
nudge set tools.endpoints api-server '{"url": "http://localhost:3000", "health": "/health"}'

# Project documentation
nudge set docs.api summary "REST API with 12 endpoints, auth via JWT"
nudge set docs.architecture overview "Microservices: api, frontend, worker + Redis"

# Reusable patterns
nudge set patterns.docker build "docker compose build --no-cache"
nudge set patterns.git commit-msg "feat(scope): description [closes #123]"
nudge set patterns.test unit "pytest -v tests/unit/"
```

### Hierarchical Organization (Slash Notation)

```bash
# Tool registry hierarchy
nudge set tools/registry/github installed "v1.0.0"
nudge set tools/registry/mcp-files endpoint "stdio://mcp-files"

# Project context
nudge set project/context/structure overview "Monorepo: api, frontend, worker"
nudge set project/context/conventions style "kebab-case files, PascalCase components"

# Environment-specific
nudge set env/dev/database url "postgresql://localhost/dev"
nudge set env/prod/database url "postgresql://db.example.com/prod"
```

### Context Summaries (JIT Detail Fetching)

Store summaries, fetch details only when needed:

```bash
# Store lightweight summary
nudge set docs.openapi summary "12 endpoints: users, posts, comments, auth"

# Store full spec separately (fetch only when needed)
nudge set docs.openapi spec '{"openapi": "3.0", "paths": {...}}'

# Agent flow:
# 1. Check summary first (lightweight)
# 2. Fetch full spec only when actually needed
```

### Cross-Cutting Concerns

```bash
# Secrets management (metadata only—never store actual secrets!)
nudge set secrets.vault location "vault.example.com/minerva/dev"
nudge set secrets.providers api "AWS Secrets Manager"

# Monitoring/observability
nudge set monitoring.metrics endpoint "http://prometheus:9090"
nudge set monitoring.traces collector "jaeger-collector:14268"

# Build/deployment metadata
nudge set ci.pipeline url "https://github.com/org/repo/actions"
nudge set deploy.staging last-commit "abc123f"
```

**Key insight:** The component parameter accepts any string identifier. Organize hints however makes sense for your project—traditional components, namespaced topics, hierarchies, or any combination.

---

## MCP API (Tools)

All methods return JSON and include a `match_explain` block where relevant.

### `nudge.set_hint`

Upsert a hint.

```json
{
  "component": "http-proxy",
  "key": "build",
  "value": { "type":"command", "shell":"bash", "cmd":"docker compose build router" },
  "meta": {
    "reason": "custom router image",
    "tags": ["build","docker"],
    "priority": 7,
    "confidence": 0.8,
    "ttl": "session",
    "scope": { "cwd_glob": ["**/http-proxy*"], "branch": ["dev","main"], "os": ["linux","darwin"] }
  },
  "if_match_version": 2
}
```

### `nudge.get_hint`

Fetch best match for `(component, key)` given a context.

```json
{
  "component": "http-proxy",
  "key": "build",
  "context": { "cwd": "/work/http-proxy", "branch": "dev", "os": "linux" }
}
```

**Result shape (abridged)**

```json
{
  "hint": { "value": "...", "meta": { /* ... */ }, "version": 3 },
  "match_explain": { "matched": true, "score": 0.91, "reasons": ["cwd matched **/http-proxy*", "branch=dev allowed"] }
}
```

### `nudge.query`

Search by component/keys/tags/regex (ranked by frecency/priority/confidence/scope specificity/recency).

```json
{
  "component": "http-proxy",
  "keys": ["build","run"],
  "tags": ["build"],
  "regex": "dock.*build",
  "context": { "cwd": "/work/http-proxy", "os": "linux" },
  "limit": 10
}
```

### `nudge.delete_hint`

```json
{ "component": "http-proxy", "key": "build" }
```

### `nudge.list_components`

```json
{}
```

### `nudge.bump`

```json
{ "component": "http-proxy", "key": "build", "delta": 1 }
```

### `nudge.export` / `nudge.import`

```json
{ "format": "json" }   // export
{ "payload": { /* store subset */ }, "mode": "merge" } // import
```

---

## Scenarios

### A) Fresh repo, agent warm-start

1. Agent enters `/work/minerva/http-proxy` on branch `dev` (Linux).
2. Calls `nudge.get_hint("http-proxy","build", context)`.
3. Nudge returns the right `docker compose` incantation + explanation.
4. Agent runs it, then calls `nudge.bump` on success.

### B) Fixing a build failure

1. Build fails with `service router not found`.
2. Agent calls `nudge.query({component:"http-proxy", tags:["build"], context, limit:3})`.
3. Tries the top scored hint; on success, calls `bump`.

### C) OS-specific directories (human first)

```bash
# Windows
nudge set http-proxy directory "c:\code\http-proxy" --scope-os windows

# macOS
nudge set http-proxy directory "/Users/imran/code/http-proxy" --scope-os darwin
```

Agents on each OS now get the right path.

### D) Ephemeral feature flag (duration TTL)

Agent sets `env.FEATURE_X=1` only for hotfix branches for 2 hours:

```json
{
  "component":"api",
  "key":"env.FEATURE_X",
  "value":"1",
  "meta":{"ttl":"PT2H","tags":["env","test"],"scope":{"branch":["hotfix/*"]}}
}
```

---

## Security & Safety

* **Local-only by default:** HTTP JSON-RPC binds to `127.0.0.1:8765`. Do not bind to `0.0.0.0` unless you understand the risks.
* **Secret guard:** Values that look like credentials (JWTs, AWS keys, long hex tokens) are rejected unless you explicitly allow them. Pretty output redacts secrets; Nudge never auto-execs commands.
* **Path normalization:** Absolute paths only for `type:"path"`, reject `..` traversal in globs and paths.

---

## Configuration

Environment variables (optional):

* `NUDGE_MAX_HINTS=5000`
* `NUDGE_SECRET_GUARD=1`     (disable with `0`)
* `NUDGE_DEFAULT_TTL=session`
* `NUDGE_HTTP=1`             (disable with `0` to turn off HTTP :8765)
* `NUDGE_LOG_LEVEL=info|debug|warn|error`

CLI flags mirror these (e.g., `--no-secret-guard`).

---

## Troubleshooting

* **`nudge: command not found`**
  Ensure your virtualenv is active or re-install: `pip install -e .`

* **Claude doesn’t see Nudge**
  Run `claude mcp list`. If missing, add again and **restart Claude**.

* **Hints not returned**
  Add `--json` and inspect `match_explain`. Often the `scope` doesn’t match the current `cwd/repo/branch/os`.

* **HTTP errors on :8765**
  Ensure you didn’t bind to an occupied port; set `NUDGE_HTTP=0` to disable if your host doesn’t need it.

---

## Development

* **Run tests:** `pytest -q`
* **Lint/format:** `ruff check . && ruff format .`
* **Release checklist:**

  * Update version
  * Verify CLI entry points
  * Smoke test with Claude/Copilot
  * Tag and publish

---

## License

MIT (or your chosen license). See `LICENSE`.

---

## Acknowledgements

Inspired by the everyday pain of “what was that build command again?” — Nudge keeps agents (and humans) in flow.
