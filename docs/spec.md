# Nudge — Session-Scoped Hint Cache (Specification)

> **Purpose:** Nudge is a tiny, opinionated, **session-persistent memory** for coding agents. It stores **small, high-value hints** (build/run commands, directories, env toggles, tiny templates) keyed by *component* and *hint key*, with optional **scoping** (cwd/repo/branch/OS) and **TTL** (often “session”).

---

## 1) Goals & Non-Goals

### Goals

* **Fast recall** of micro-facts: `component → {key → value(+meta)}`
* **Session persistence** (in-memory), optional import/export for warm starts
* **Simple MCP surface** for agents; **human-friendly CLI** for developers
* **Scoped retrieval**: only return hints that match current context (cwd/repo/branch/OS/env)
* **Explainability**: always include *why* a hint matched (score + reasons)
* **Safety**: guard against secrets, unsafe paths, and accidental execution

### Non-Goals

* Long-horizon planning, task graphs, issue tracking
* Multi-user, cross-machine syncing (keep local/session-first)
* Heavy persistence or databases by default

---

## 2) Core Concepts

* **Component**: a service/module/folder name (“`http-proxy`”, “`auth`”).
* **Hint**: a key/value pair (e.g., `build → "docker compose build router"`), with metadata.
* **Scope**: conditions under which a hint is *eligible*: cwd patterns, repo, branch, OS, env.
* **Context**: the runtime facts supplied by a caller (agent or CLI): `{cwd, repo, branch, os, env}`.
* **TTL**: “`session`” or ISO-8601 duration (e.g., `"PT2H"`). Expired hints are ignored/evicted.
* **Frecency**: frequency × recency score that rises on use (via `bump`).

---

## 3) Data Model

```ts
type NudgeStore = {
  schema_version: "1.0";
  created_at: string; // ISO
  session_id: string;

  components: Record<string, ComponentHints>;
};

type ComponentHints = {
  hints: Record<string, Hint>; // key -> hint
};

type Hint = {
  value: HintValue;
  meta: HintMeta;
  version: number;         // increments on update
  created_at: string;      // ISO
  updated_at: string;      // ISO
  last_used_at?: string;   // ISO
  use_count?: number;      // bump target
};

type HintValue =
  | string
  | {
      type: "command";
      shell?: "bash" | "sh" | "powershell" | "cmd";
      cmd: string;
    }
  | {
      type: "path";
      os?: Array<"linux" | "darwin" | "windows">;
      abs: string;
    }
  | {
      type: "template";
      format: "mustache" | "handlebars" | "jinja" | "interpolate";
      body: string;
      defaults?: Record<string, string>;
    }
  | {
      type: "json";
      data: unknown;
    };

type HintMeta = {
  reason?: string;
  tags?: string[];               // e.g., ["build","docker"]
  priority?: number;             // 1–10
  confidence?: number;           // 0.0–1.0
  ttl?: "session" | string;      // ISO-8601 duration
  sensitivity?: "secret" | "normal";

  scope?: {
    cwd_glob?: string[];         // micromatch/fast-glob style
    repo?: string | string[];    // e.g., "git:org/repo" or "file:///…"
    branch?: string[];           // ["main","dev"]
    os?: Array<"linux" | "darwin" | "windows">;
    env_required?: string[];     // names that must be set
    env_match?: Record<string, string | string[]>; // exact matches
  };

  source?: "user" | "agent" | "tool-output" | "file-import";
  added_by?: string;             // free-form; “agent:codex”
};
```

---

## 4) Context & Matching

```ts
type NudgeContext = {
  cwd?: string;
  repo?: string;
  branch?: string;
  os?: "linux" | "darwin" | "windows";
  env?: Record<string, string | undefined>;
  files_open?: string[]; // optional hints for ranking
};
```

### Eligibility filter (hard gate)

A hint is eligible iff all specified scope conditions match:

* `cwd_glob`: at least one glob matches `context.cwd`
* `repo`: context.repo equals one of meta.repo
* `branch`: context.branch is included
* `os`: context.os is included
* `env_required`: all names exist in `context.env`
* `env_match`: every listed key equals one of the allowed values

### Ranking (soft order)

Score each eligible hint:

```
score = 0.30 * frecency(use_count, last_used_at)
      + 0.20 * (priority/10)
      + 0.20 * confidence
      + 0.20 * scope_specificity  // more fields specified => higher
      + 0.10 * recency(updated_at)
```

Return top-N sorted by `score` (default N=1 for `get`).

Each read response includes:

```json
"match_explain": {
  "matched": true,
  "score": 0.91,
  "reasons": [
    "cwd matched **/http-proxy*",
    "branch=dev allowed",
    "recently used (3m ago)"
  ]
}
```

---

## 5) MCP Surface (JSON-RPC over the MCP transport)

> **Transport**: Nudge uses STDIO for MCP communication. The server runs in two modes:
> - **PRIMARY**: First `nudge serve` becomes PRIMARY, running both STDIO MCP + HTTP JSON-RPC server (port 8765 default)
> - **PROXY**: Additional `nudge serve` instances detect PRIMARY and become PROXY, forwarding STDIO MCP calls to PRIMARY via HTTP
>
> This architecture allows multiple MCP clients (e.g., multiple Claude Code instances) to share the same in-memory hint store. Payloads below are transport-agnostic.

### Methods

1. **`nudge.set_hint`** — upsert a hint
   **params**

   ```json
   {
     "component": "http-proxy",
     "key": "build",
     "value": {"type":"command","shell":"bash","cmd":"docker compose build router"},
     "meta": {
       "reason": "custom router image",
       "tags": ["build","docker"],
       "priority": 7,
       "confidence": 0.8,
       "ttl": "session",
       "scope": {"cwd_glob":["**/http-proxy*"], "branch":["dev","main"], "os":["linux","darwin"]}
     },
     "if_match_version": 12   // optional optimistic concurrency
   }
   ```

   **result**

   ```json
   {"hint": { /* full Hint */ }}
   ```

2. **`nudge.get_hint`** — fetch best match for (component,key)
   **params**

   ```json
   {"component":"http-proxy","key":"build","context":{"cwd":"/work/http-proxy","branch":"dev","os":"linux"}}
   ```

   **result**

   ```json
   {
     "hint": { /* full Hint */ },
     "match_explain": { "matched": true, "score": 0.91, "reasons": ["..."] }
   }
   ```

3. **`nudge.query`** — search by component/keys/tags/regex
   **params**

   ```json
   {
     "component": "http-proxy",
     "keys": ["build","run"],
     "tags": ["build"],
     "regex": "dock.*build",
     "context": {"cwd":"/work/http-proxy","os":"linux"},
     "limit": 10
   }
   ```

   **result**

   ```json
   {"hints": [{ "hint": { /* Hint */ }, "score": 0.88, "match_explain": { ... } }]}
   ```

4. **`nudge.delete_hint`**
   **params** `{"component":"http-proxy","key":"build"}`
   **result** `{"deleted": true, "previous": { /* Hint */ }}`

5. **`nudge.list_components`**
   **result** `{"components": [{"name":"http-proxy","hint_count":3}, ...]}`

6. **`nudge.bump`** — increase frecency after successful use
   **params** `{"component":"http-proxy","key":"build","delta":1}`
   **result** `{"hint": { /* updated counts/timestamps */ }}`

7. **`nudge.export`**
   **params** `{"format":"json"}`
   **result** `{"payload": { /* NudgeStore subset */ }}`

8. **`nudge.import`**
   **params** `{"payload": { /* NudgeStore subset */ }, "mode":"merge"}`
   **result** `{"imported": 12, "skipped": 0}`

### Error Model

Errors are JSON-RPC errors with `code` and `data.reason`:

* `E_NOT_FOUND` (40401) — component or key not found
* `E_INVALID` (40001) — schema/type/constraint violation
* `E_CONFLICT` (40901) — `if_match_version` mismatch
* `E_SECRET_REJECTED` (40002) — secret guard tripped
* `E_SCOPE_INVALID` (40003) — illegal glob or path traversal risk
* `E_QUOTA` (42901) — store size/limits exceeded

---

## 6) CLI for Humans

> The CLI is a thin client that talks to the running Nudge server via HTTP JSON-RPC (localhost).

### Server Management

```bash
# Start server (auto-detects PRIMARY or PROXY mode)
nudge serve [--port PORT]  # default port: 8765

# Check server status
nudge status

# Stop server
nudge stop

# Override port for any command
nudge -p PORT <command>
```

### Hint Management

#### Add / Upsert

```bash
# minimal
nudge set http-proxy build "docker compose build router"

# with scope & metadata
nudge set http-proxy build "docker compose build router" \
  --tags build,docker --priority 7 --confidence 0.8 --ttl session \
  --scope-cwd-glob "**/http-proxy*" \
  --scope-branch dev,main --scope-os linux,darwin
```

#### Get (auto-context)

```bash
# context auto-filled from env and repo when omitted
nudge get http-proxy build

# explicit context
nudge get http-proxy build --cwd "$PWD" \
  --branch "$(git rev-parse --abbrev-ref HEAD)" \
  --os "$(uname | tr '[:upper:]' '[:lower:]')"
```

#### Query / List

```bash
nudge query --component http-proxy --tags build --limit 5
nudge ls                    # list all components (alias: list-components)
nudge ls <component>        # list keys in a component
```

#### Delete / Bump

```bash
nudge delete http-proxy build
nudge bump http-proxy build --delta 1
```

#### Import / Export

```bash
nudge export --format json > nudge-session.json
nudge import ./seed-hints.json
```

### Output Modes

* **Pretty** (default human-readable)
* **JSON** (`--json`) returns the exact MCP result for scripting

### Context Inference (CLI)

* `cwd` = `$PWD`
* `repo` = from `git remote get-url origin` (fallback: `file://` path)
* `branch` = `git rev-parse --abbrev-ref HEAD`
* `os` = normalized from `uname` or Windows environment
* `env` = current process env

---

## 7) Scenarios (End-to-End)

### A) Warm Start (Agent)

1. Agent opens repo `/work/minerva/http-proxy (branch=dev, os=linux)`.
2. Agent calls:

   ```json
   {"method":"nudge.get_hint","params":{"component":"http-proxy","key":"build","context":{"cwd":"/work/minerva/http-proxy","branch":"dev","os":"linux"}}}
   ```
3. Nudge returns the build command plus `match_explain`.
4. Agent runs the command; upon success, calls `nudge.bump` to reinforce.

### B) Fixing a Build Error (Agent)

1. Build fails with “`service router not found`”.
2. Agent calls:

   ```json
   {"method":"nudge.query","params":{"component":"http-proxy","tags":["build"],"context":{"cwd":"/work/minerva/http-proxy","os":"linux"},"limit":3}}
   ```
3. Nudge returns a ranked list; top item includes `docker compose build router`.
4. Agent retries with suggested command; on success calls `bump`.

### C) Platform-Specific Paths (Human + Agent)

1. Developer on Windows adds:

   ```bash
   nudge set http-proxy directory "c:\code\http-proxy" --scope-os windows
   ```
2. Teammate on macOS adds:

   ```bash
   nudge set http-proxy directory "/Users/dev/code/http-proxy" --scope-os darwin
   ```
3. Agents on each OS call `get` and automatically receive the correct path.

### D) Ephemeral Toggle with Duration TTL (Agent)

1. During a hotfix, tests require `FEATURE_X=1` for two hours:

   ```json
   {
     "method":"nudge.set_hint",
     "params":{
       "component":"api",
       "key":"env.FEATURE_X",
       "value":"1",
       "meta":{"ttl":"PT2H","tags":["env","test"],"scope":{"branch":["hotfix/*"]}}
     }
   }
   ```
2. After two hours, the hint silently expires.

### E) Human Seed + Agent Consumption

1. Developer seeds session:

   ```bash
   nudge import ./nudge-seed.json
   ```
2. Agent immediately benefits from preloaded hints without writing any files.

---

## 8) Safety & Hygiene

* **Secret Guard (default on):**

  * Reject values that look like credentials (AWS key patterns, 32–64 hex, JWT `xxxxx.yyyyy.zzzzz`) unless `--allow-secret` or `meta.sensitivity="secret"`.
  * Redact secret values in pretty output; never auto-execute commands.
* **Path Normalization:**

  * Normalize and validate `path`/`cwd_glob`; reject `..` traversal or non-absolute path values for `type:"path"`.
* **Command Objects:**

  * Commands are returned as data (never executed by Nudge).
* **Rate/Dedup on Notifications (if host supports events):**

  * At most *N* suggestions per 10 minutes; dedupe identical hints.

---

## 9) Lifecycle & Persistence

* **In-Memory Store:** cleared when the process ends (session).
* **Single-Instance Architecture:**
  * Lock mechanism ensures only one PRIMARY server per machine/container
  * PID file location:
    * Linux/macOS: `/tmp/nudge/server.pid`
    * Windows: `%LOCALAPPDATA%\nudge\server.pid`
  * PID file format: `{"pid": 12345, "port": 8765, "started": "2025-11-04T..."}`
  * Subsequent `nudge serve` calls become PROXY servers (forwarding to PRIMARY)
* **TTL Eviction:** periodic sweep removes expired hints.
* **Size Limits (defaults):**

  * Max components: 500
  * Max hints per component: 200
  * Max total hints: 5,000
* **Import/Export:** JSON payload of the store or subsets for warm starts.
* **Metrics (optional):** `use_count`, `last_used_at`, top tags.

---

## 10) Configuration

Environment variables (optional):

* `NUDGE_MAX_HINTS=5000`
* `NUDGE_SECRET_GUARD=1` (disable with `0`)
* `NUDGE_DEFAULT_TTL=session`
* `NUDGE_LOG_LEVEL=info|debug|warn|error`

Server port configuration:

* `nudge serve --port PORT` — set server port (default: 8765)
* `nudge -p PORT <command>` — override port for any CLI command
* Port discovery priority: CLI flag > PID file > default (8765)
* Auto-increment: if port is taken, server tries PORT+1, PORT+2, etc.

CLI flags mirror environment variables (e.g., `--no-secret-guard`).

---

## 11) Multi-Instance Architecture

Nudge implements a single-instance server design with PRIMARY/PROXY mode support:

### PRIMARY Server

When `nudge serve` is called and no server is running:

* Becomes **PRIMARY** server
* Runs HTTP JSON-RPC server on specified port (default: 8765)
* Runs STDIO MCP server for direct MCP communication
* Creates PID file with lock: `{"pid": N, "port": P, "started": "..."}`
* Holds the authoritative in-memory hint store

### PROXY Server

When `nudge serve` is called and a PRIMARY is already running:

* Detects existing PRIMARY via PID file
* Becomes **PROXY** server
* Runs STDIO MCP server only
* Forwards all MCP tool calls to PRIMARY via HTTP JSON-RPC
* No in-memory store, no HTTP server, no PID file

### Multi-Client Sharing

All clients share the same hints via this architecture:

```
┌─────────────┐
│  Terminal   │────HTTP:8765────┐
└─────────────┘                 │
                                ▼
┌─────────────┐           ┌──────────┐
│Claude Code#1│──STDIO───→│ PRIMARY  │
└─────────────┘           │  Server  │
                          │          │
┌─────────────┐           │ - Store  │
│Claude Code#2│──STDIO──┐ │ - HTTP   │
└─────────────┘         │ │ - STDIO  │
                        ▼ └──────────┘
                   ┌─────────┐    ▲
                   │ PROXY   │    │
                   │ Server  │────┘
                   └─────────┘
                   HTTP:8765
```

### Benefits

* **Single source of truth**: All clients access the same in-memory store
* **Multiple MCP clients**: Each Claude Code instance gets its own STDIO connection
* **Shared state**: Hints added by CLI are immediately visible to all MCP clients
* **Automatic failover**: If PRIMARY dies, next `nudge serve` becomes new PRIMARY

---

## 12) Minimal Implementation Notes (non-normative)

* **Language:** any; store can be a plain JS/TS/Go/Python map.
* **Indices:** maintain small indices by `component`, `tags` to speed `query`.
* **Glob:** use micromatch/fast-glob style; evaluate against normalized `cwd`.
* **Frecency:** exponential decay on `use_count` with time since `last_used_at`.
* **Concurrency:** include `version` numbers; support `if_match_version` on `set`.

---

## 12) Testing Checklist

* CRUD: set/get/query/delete across OS and branches
* Scoping: each scope field independently and in combination
* TTL: expiration behavior
* Secret guard: reject + allow override path
* Ranking: frecency/priority/confidence tie-breakers
* Error cases: invalid schema, conflicts, quotas
* CLI: pretty vs `--json`, context inference

---

## 13) Appendix A — JSON Schemas (abridged)

**`SetHintParams`**

```json
{
  "type":"object",
  "required":["component","key","value"],
  "properties":{
    "component":{"type":"string","minLength":1},
    "key":{"type":"string","minLength":1},
    "value":{},
    "meta":{"type":"object"},
    "if_match_version":{"type":"integer","minimum":0}
  }
}
```

**`GetHintParams`**

```json
{
  "type":"object",
  "required":["component","key"],
  "properties":{
    "component":{"type":"string"},
    "key":{"type":"string"},
    "context":{"$ref":"#/definitions/NudgeContext"}
  },
  "definitions":{
    "NudgeContext":{
      "type":"object",
      "properties":{
        "cwd":{"type":"string"},
        "repo":{"type":"string"},
        "branch":{"type":"string"},
        "os":{"enum":["linux","darwin","windows"]},
        "env":{"type":"object","additionalProperties":{"type":"string"}}
      }
    }
  }
}
```

(Other methods follow analogous shapes.)

---

## 14) Appendix B — Example CLI Transcript

```bash
$ nudge set http-proxy build "docker compose build router" \
    --tags build,docker --priority 7 --ttl session --scope-cwd-glob "**/http-proxy*"

✔ upserted hint http-proxy/build (v3)
  score base: priority=7 tags=build,docker ttl=session scope=cwd_glob

$ nudge get http-proxy build
value: docker compose build router
match:
  score: 0.92
  reasons:
    - cwd matched **/http-proxy*
    - recently used (5m ago)

$ nudge bump http-proxy build
↑ bumped frecency: use_count=4 last_used_at=now
```

---

## 15) Versioning

* **`schema_version`:** start at `"1.0"`. Server rejects unknown future versions on import.
* **Breaking changes:** increment major (`2.0`); keep MCP method names stable when possible.

---

### TL;DR

* **Agents** call `get_hint` before build/test/run; call `bump` after successful use; add facts via `set_hint`; use `query` on errors.
* **Humans** use `nudge set/get/query/bump/delete` with smart defaults and `--json` for scripts.
* **Nudge** stays fast, scoped, explainable, and safe—*a tiny memory that makes agents feel prepared every session.*
