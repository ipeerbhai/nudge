# Nudge

A lightweight memory system that stores small, high-value hints (build commands, directories, env vars) for AI coding agents. Hints are matched by context (cwd, repo, branch, OS) and ranked by relevance.

## Concept of Operations
Coding agents often forget things as they code. We often have to "re-aim" them when they forget. Nudge is meant to help with this problem. It is essentially a dictionary of dictionaries. The top level dictionary's keys are "components", and the bottom level dictionary is "hints".

So, Imagine that you're working on an http-proxy of some sort in a docker container. The code agent is doing well, but once in a while, forgets that the code is in docker. You'd define the component as http-proxy, and the hint as build, like this:
nudge set http-proxy build "docker compose build http-proxy".

**Note:** Nudge runs as a single PRIMARY server per machine. When you run `nudge serve`:
- If no server running → becomes PRIMARY (STDIO MCP + HTTP JSON-RPC on port 8765)
- If server running → becomes PROXY (STDIO MCP forwarding to PRIMARY via HTTP)
- All CLI commands use HTTP. All MCP clients get STDIO interface that shares the same data.

That's it. Whole idea. There's tags and other things that you can add to make it faster/easier to search, but the entire concept is that you have a store of hints per component that you and the llm share. You can add hints. The llm can add hints. You can use the hints. The llm can use the hints. No filesystem. No persistence.

## Installation

Nudge works with any MCP-compatible coding assistant. Choose your system below:

### A. Claude Code

**1. Install the package:**

```bash
cd /path/to/nudge
pip install -e .
```

**2. Add to Claude Code MCP configuration:**

**Option A: Using CLI (Recommended)**
```bash
# Default scope is 'local' (all projects for this user)
claude mcp add nudge -- nudge serve

# Verify it was added
claude mcp list
```

**Option B: Project-specific configuration**

Create `.mcp.json` in your project root:
```bash
cat > .mcp.json << 'EOF'
{
  "mcpServers": {
    "nudge": {
      "command": "nudge",
      "args": ["serve"]
    }
  }
}
EOF
```

**Note:** Use `claude mcp add --scope project` if you want project-specific configuration via CLI.

**3. Restart Claude Code**

Exit and restart Claude Code completely.

Nudge MCP tools are now available, but Claude Code doesn't know WHEN to use them yet.

**4. Add instructions so Claude Code knows when to use nudge:**

Create a `CLAUDE.md` file to tell Claude Code how to use nudge automatically. You have two options:

**Option A: Project-level** (recommended for team projects)
=== CLAUDE.md
# Nudge Usage Instructions

## When to Use Nudge

You have access to a hint system called **nudge** that stores commands, paths, and configuration for this project.

### Before Running Commands

**Always check nudge first** before running build, test, deploy, or project-specific commands:

```javascript
// Example: Before building
const hint = await nudge.get_hint("component-name", "build", {
  cwd: process.cwd(),
  branch: currentGitBranch,
  os: platform
});
if (hint) {
  // Use the stored command
  runCommand(hint.value);
}
```

### When to Store Hints

**Store corrections immediately** when the user corrects your commands:

```javascript
// User says: "No, use 'docker compose build' not 'docker build'"
await nudge.set_hint("http-proxy", "build", "docker compose build", {
  meta: {
    tags: ["build", "docker"],
    reason: "User correction",
    ttl: "session"
  }
});
```

### After Successful Hints

**Bump frecency** after successfully using a hint:

```javascript
await nudge.bump("component-name", "key");
```

### Common hints to Check

- `build` - Build commands
- `test` - Test commands
- `deploy` - Deployment commands
- `start` - Start/run commands
- `env` - Environment setup
- `paths` - Important directories

### Query for Discovery
When unsure components are available with hints:

```javascript
const components = await nudge.list_components();
```

When unsure what's hints are available for a component:

```javascript
const hints = await nudge.query({
  component: "component-name",
  limit: 10
});
```
===
**Option B: User-level** (your personal preferences across all projects)
# macOS/Linux
 ~/.claude/CLAUDE.md
# [same content as option A]
EOF

# Windows (PowerShell)
New-Item -Path "$env:USERPROFILE\.claude\CLAUDE.md" -ItemType File -Force
# [edit and paste content from option A]
===

**5. Verify the setup:**

Start a new Claude Code session and ask:
```
"Build the http-proxy component"
```

You should see me:
1. Query nudge first: `nudge.get_hint("http-proxy", "build")`
2. Either use the stored command or ask for guidance
3. Store the command if you provide one
4. Bump the hint after successful use

**How Multiple Claude Code Instances Work:**

- First Claude Code instance → becomes PRIMARY server (holds the hint store)
- Additional Claude Code instances → become PROXY servers (forward to PRIMARY)
- All instances share the same hints through the PRIMARY's in-memory store
- CLI commands also connect to the PRIMARY via HTTP

---

### B. OpenAI Codex

**1. Install the package:**

```bash
cd /path/to/nudge
pip install -e .
```

**2. Add to Codex MCP configuration:**

Option A: Using the CLI command (recommended):
```bash
codex mcp add nudge -- nudge serve
```

Option B: Manually edit `~/.codex/config.toml`:
```toml
[mcp_servers.nudge]
command = "nudge"
args = ["serve"]
```

**3. Restart Codex**

```bash
# If running, restart Codex CLI
codex
```

**4. Add instructions so Codex knows when to use nudge:**

Create an `AGENTS.md` file (Codex uses AGENTS.md, not CLAUDE.md). You have two options:

**Option A: Project-level** (recommended for team projects)
```bash
# In your project root
cat > AGENTS.md << 'EOF'
# Nudge Usage Instructions

## When to Use Nudge

You have access to a hint system called **nudge** that stores commands, paths, and configuration for this project.

### Before Running Commands

**Always check nudge first** before running build, test, deploy, or project-specific commands:

```javascript
// Example: Before building
const hint = await nudge.get_hint("component-name", "build", {
  cwd: process.cwd(),
  branch: currentGitBranch,
  os: platform
});
if (hint) {
  // Use the stored command
  runCommand(hint.value);
}
```

### When to Store Hints

**Store corrections immediately** when the user corrects your commands:

```javascript
// User says: "No, use 'docker compose build' not 'docker build'"
await nudge.set_hint("http-proxy", "build", "docker compose build", {
  meta: {
    tags: ["build", "docker"],
    reason: "User correction",
    ttl: "session"
  }
});
```

### After Successful Hints

**Bump frecency** after successfully using a hint:

```javascript
await nudge.bump("component-name", "key");
```

### Common Components to Check

- `build` - Build commands
- `test` - Test commands
- `deploy` - Deployment commands
- `start` - Start/run commands
- `env` - Environment setup
- `paths` - Important directories

### Query for Discovery

When unsure what's available:

```javascript
const hints = await nudge.query({
  component: "component-name",
  limit: 10
});
```
EOF
```

**Option B: Global (user-level)** - Via config file

Edit `~/.codex/config.toml` and add:
```toml
experimental_instructions_file = "/path/to/your/global-instructions.md"
```
Then create that file with the same content as above.

**5. Verify the setup:**

Start a Codex session and ask:
```
"Build the http-proxy component"
```

You should see Codex:
1. Query nudge first: `nudge.get_hint("http-proxy", "build")`
2. Either use the stored command or ask for guidance
3. Store the command if you provide one
4. Bump the hint after successful use

---

### C. OpenCode

**1. Install the package:**

```bash
cd /path/to/nudge
pip install -e .
```

**2. Add to OpenCode MCP configuration:**

Edit `~/.config/opencode/opencode.json` (or create `opencode.json` in your project root):

```json
{
  "mcp": {
    "nudge": {
      "type": "local",
      "command": ["nudge", "serve"],
      "enabled": true,
      "environment": {}
    }
  },
  "tools": {
    "nudge_*": true
  }
}
```

**3. Restart OpenCode**

```bash
# Start OpenCode in your project
cd /your/project
opencode
```

**4. Add instructions so OpenCode knows when to use nudge:**

Create an `AGENTS.md` file (OpenCode uses AGENTS.md, not CLAUDE.md). You have two options:

**Option A: Project-level** (recommended for team projects)
```bash
# In your project root
cat > AGENTS.md << 'EOF'
# Nudge Usage Instructions

## When to Use Nudge

You have access to a hint system called **nudge** that stores commands, paths, and configuration for this project.

### Before Running Commands

**Always check nudge first** before running build, test, deploy, or project-specific commands:

```javascript
// Example: Before building
const hint = await nudge.get_hint("component-name", "build", {
  cwd: process.cwd(),
  branch: currentGitBranch,
  os: platform
});
if (hint) {
  // Use the stored command
  runCommand(hint.value);
}
```

### When to Store Hints

**Store corrections immediately** when the user corrects your commands:

```javascript
// User says: "No, use 'docker compose build' not 'docker build'"
await nudge.set_hint("http-proxy", "build", "docker compose build", {
  meta: {
    tags: ["build", "docker"],
    reason: "User correction",
    ttl: "session"
  }
});
```

### After Successful Hints

**Bump frecency** after successfully using a hint:

```javascript
await nudge.bump("component-name", "key");
```

### Common Components to Check

- `build` - Build commands
- `test` - Test commands
- `deploy` - Deployment commands
- `start` - Start/run commands
- `env` - Environment setup
- `paths` - Important directories

### Query for Discovery

When unsure what's available:

```javascript
const hints = await nudge.query({
  component: "component-name",
  limit: 10
});
```
EOF
```

**Option B: Global (user-level)**
```bash
# Create global instructions
cat > ~/.config/opencode/AGENTS.md << 'EOF'
# [same content as above]
EOF
```

**5. Verify the setup:**

Start an OpenCode session and ask:
```
"Build the http-proxy component"
```

You should see OpenCode:
1. Query nudge first: `nudge.get_hint("http-proxy", "build")`
2. Either use the stored command or ask for guidance
3. Store the command if you provide one
4. Bump the hint after successful use

---

## Adding Hints for the LLM

Use the CLI to add hints that the LLM can retrieve:

```bash
# Basic hint
nudge set my-project build "npm run build"

# Hint with context scoping
nudge set api test "pytest tests/" \
  --tags test,python \
  --scope-cwd-glob "**/api/**" \
  --scope-branch main,dev
```

The LLM will automatically find and use these hints when working in matching contexts.

## Available MCP Tools

- `nudge.get_hint` - Retrieve a hint by component/key
- `nudge.set_hint` - Store a new hint
- `nudge.query` - Search hints by tags/component
- `nudge.bump` - Increase frecency after successful use
- `nudge.list_components` - List all stored components
- `nudge.delete_hint` - Remove a hint
- `nudge.export` / `nudge.import` - Backup/restore hints

## Example Usage

```bash
# Store build commands for frontend and backend componets
nudge set frontend build "npm run build"
nudge set backend build "docker compose up --build"

# Store test commands
nudge set backend test "pytest -v" --tags test

# List all components
nudge ls

# List keys in a specific component
nudge ls backend
```

The LLM will automatically retrieve these hints when working on the frontend or backend, matching by your current directory and context.

## How It Works

- **Single-instance design**: One PRIMARY server per machine; multiple PROXY servers for multiple Claude Code instances; all share the same in-memory store
- **Safe by default**: Guards against accidental secret storage
- **Session-persistent**: Hints stored in memory, cleared on restart

### Architecture

```
┌─────────────┐
│  Terminal   │────HTTP:8765────┐
│  (CLI)      │                 │
└─────────────┘                 ▼
                          ┌──────────┐
┌─────────────┐           │ PRIMARY  │
│Claude Code#1│──STDIO───→│  Server  │
└─────────────┘           │          │
                          │ - Store  │
┌─────────────┐           │ - HTTP   │
│Claude Code#2│──STDIO──┐ │ - STDIO  │
└─────────────┘         │ └──────────┘
                        ▼      ▲
                   ┌─────────┐ │
                   │ PROXY   │─┘
                   │ Server  │
                   └─────────┘
                   HTTP:8765
```

All clients (CLI + Claude Code instances) share the same hints through the PRIMARY server.

## Server Management

The server runs on HTTP port 8765 by default. You can customize this:

```bash
# Start server (auto-detects PRIMARY or PROXY mode)
nudge serve --port 9000

# Check if server is running
nudge status

# Stop the server
nudge stop
```

### PID File

The server creates a PID file at:
- **Linux/macOS**: `/tmp/nudge/server.pid`
- **Windows**: `%LOCALAPPDATA%\nudge\server.pid`

Contains: `{"pid": 12345, "port": 8765, "started": "2025-11-04T..."}`

CLI commands auto-discover the server port from this PID file. You can also specify a port explicitly:

```bash
nudge -p 9000 ls
```

## CLI Reference

```bash
nudge serve [--port PORT]             # Start PRIMARY or PROXY (auto, default: 8765)
nudge status                          # Check server status
nudge stop                            # Stop server
nudge set <component> <key> <value>   # Add hint
nudge get <component> <key>           # Retrieve hint
nudge query --component <name>        # Search hints
nudge delete <component> <key>        # Delete hint
nudge bump <component> <key>          # Mark as used
nudge ls                              # List all components
nudge ls <component>                  # List keys in a component
nudge export > backup.json            # Backup
nudge import backup.json              # Restore
nudge -p PORT <command>               # Override port for any command
```

## License

MIT - See [LICENSE](LICENSE)

## Documentation

Full specification: [docs/spec.md](docs/spec.md)
