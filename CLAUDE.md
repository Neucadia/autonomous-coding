# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an autonomous coding agent that builds complete applications over multiple sessions using a two-agent pattern (initializer + coding agent). It leverages the Claude Agent SDK to implement features iteratively, tracking progress in a SQLite database via an MCP server.

## Key Architecture

### Two-Agent Pattern

1. **Initializer Agent (First Session)**
   - Triggered when no features exist in the database
   - Reads `app_spec.txt` from project's `prompts/` directory
   - Creates comprehensive feature list (150-400+ features) using `feature_create_bulk` MCP tool
   - Features stored in SQLite database (`features.db`) as single source of truth

2. **Coding Agent (Subsequent Sessions)**
   - Gets next feature via `feature_get_next` MCP tool
   - Implements one feature at a time
   - Marks features as passing via `feature_mark_passing` MCP tool
   - Can skip blocked features via `feature_skip` MCP tool
   - Auto-continues every 3 seconds between sessions

### Core Components

- **`agent.py`**: Main agent loop, session management, auto-continuation logic
- **`client.py`**: Claude SDK client creation with security configuration
- **`security.py`**: Bash command allowlist hook (defense-in-depth security)
- **`prompts.py`**: Template loading with project-specific fallback chain
- **`progress.py`**: SQLite-based progress tracking and webhook notifications
- **`mcp_server/feature_mcp.py`**: MCP server providing feature management tools
- **`api/database.py`**: SQLite database schema (Feature model)
- **`start.py`**: Interactive CLI for creating/continuing projects

### Project Structure

```
autonomous-coding/
├── start.sh / start.bat         # Entry points (setup + launch)
├── start.py                     # Interactive menu
├── autonomous_agent_demo.py     # Agent harness
├── agent.py / client.py         # Core agent logic
├── security.py                  # Bash allowlist
├── prompts.py / progress.py     # Utilities
├── mcp_server/feature_mcp.py    # Feature management MCP
├── api/{database,migration}.py  # Database layer
├── .claude/
│   ├── commands/create-spec.md  # Interactive spec creation
│   └── templates/               # Prompt templates
└── generations/{project}/       # Generated projects
    ├── prompts/
    │   ├── app_spec.txt         # Project specification
    │   ├── initializer_prompt.md
    │   └── coding_prompt.md
    ├── features.db              # SQLite feature database
    └── [generated code]
```

## Common Commands

### Starting the Agent

```bash
# Interactive launcher (recommended)
./start.sh  # macOS/Linux
start.bat   # Windows

# Direct invocation
python autonomous_agent_demo.py --project-dir my_project

# Limit iterations for testing
python autonomous_agent_demo.py --project-dir my_project --max-iterations 5
```

### Working with the Database

The agent uses MCP tools to interact with `features.db`. Direct SQLite access for debugging:

```bash
cd generations/{project}
sqlite3 features.db

# Useful queries
SELECT COUNT(*) FROM features WHERE passes = 1;  # Count passing
SELECT id, category, name FROM features WHERE passes = 0 ORDER BY priority LIMIT 5;  # Next features
```

### Testing Generated Applications

```bash
cd generations/{project}
./init.sh           # If created by agent
# Or manually:
npm install
npm run dev
```

### Development Commands

```bash
# Run security tests
python test_security.py

# Check Python dependencies
pip install -r requirements.txt

# Test MCP server directly
python -m mcp_server.feature_mcp
```

## Security Model

Multi-layered defense-in-depth approach (configured in `client.py`):

1. **OS Sandbox**: Bash commands run in isolated environment
2. **Filesystem Restrictions**: All file operations restricted to project directory (`./**` permissions)
3. **Bash Allowlist Hook**: Only whitelisted commands permitted (see `security.py`)

### Allowed Commands

Defined in `security.py::ALLOWED_COMMANDS`:
- File inspection: `ls`, `cat`, `head`, `tail`, `wc`, `grep`
- Node.js: `npm`, `npx`, `pnpm`, `node`
- Expo/React Native: `expo`, `eas`
- Git: `git`
- Docker: `docker` (for databases)
- Process management: `ps`, `lsof`, `sleep`, `kill`, `pkill` (dev processes only)
- File operations: `cp`, `mkdir`, `mv`, `rm`, `touch`, `chmod` (+x only)
- Scripts: `sh`, `bash`, `init.sh`
- Network: `curl`

**Special validation** for `pkill` (only dev processes), `chmod` (+x only), `init.sh` (path restricted).

## MCP Server Integration

The agent uses three MCP servers (configured in `client.py`):

### 1. Playwright MCP (Browser Automation)

```bash
npx @playwright/mcp@latest --headless
```

Tools: `browser_navigate`, `browser_click`, `browser_type`, `browser_screenshot`, etc.

### 2. Features MCP (Database Management)

```bash
python -m mcp_server.feature_mcp
```

**Available Tools:**

- `feature_get_stats()`: Get passing/total counts
- `feature_get_next()`: Get highest-priority pending feature
- `feature_get_for_regression(limit=3)`: Get random passing features for testing
- `feature_mark_passing(feature_id)`: Mark feature as implemented
- `feature_skip(feature_id, reason)`: Skip feature and mark for user review
- `feature_create_bulk(features)`: Create multiple features (initializer only)
- `feature_get_skipped()`: Get features skipped and awaiting user approval
- `feature_approve(feature_id)`: Approve a skipped feature to be worked on again
- `feature_reject_skip(feature_id)`: Permanently reject a skipped feature
- `feature_record_failure(feature_id, error_message)`: Record a failure for stuck loop detection

### 3. Expo MCP (React Native/Expo Development)

```bash
npx @anthropic-ai/claude-mcp-server-expo
```

**Remote Capabilities (always available):**

- `learn`: Retrieve Expo how-to guides on specific topics
- `search_documentation`: Query Expo docs using natural language
- `add_library`: Install Expo packages via `npx expo install`
- `generate_claude_md`: Create CLAUDE.md configuration files
- `generate_agents_md`: Create AGENTS.md files

**Local Capabilities (requires local dev server with `expo-mcp` package):**

- `expo_router_sitemap`: Display expo-router sitemap output
- `open_devtools`: Launch React Native DevTools
- `automation_tap`: Tap screen coordinates
- `automation_take_screenshot`: Capture full device screenshots
- `automation_find_view_by_testid`: Locate views by testID
- `automation_tap_by_testid`: Tap views by testID
- `automation_take_screenshot_by_testid`: Screenshot specific views by testID

**Note:** For local capabilities, the project must have `expo-mcp` installed and `EXPO_UNSTABLE_MCP_SERVER=1` environment variable set when running the dev server.

## Prompt Template System

Prompts follow a fallback chain:

1. **Project-specific**: `generations/{project}/prompts/{name}.md`
2. **Base template**: `.claude/templates/{name}.template.md`

Files:
- `app_spec.txt`: Application specification (user-provided or generated via `/create-spec`)
- `initializer_prompt.md`: First session instructions (feature creation)
- `coding_prompt.md`: Continuation session instructions (feature implementation)

Prompts are copied to project directories during scaffolding and can be customized per-project.

## Session Workflow

### Initializer Session
1. Read `app_spec.txt`
2. Generate 150-400+ features using `feature_create_bulk`
3. Set up project structure (package.json, git init, etc.)

### Coding Sessions
1. **Orient**: Check `app_spec.txt`, `claude-progress.txt`, git log, feature stats
2. **Start servers**: Run `init.sh` if it exists
3. **Regression test**: Get passing features via `feature_get_for_regression`, verify still working
4. **Get next feature**: Use `feature_get_next`
5. **Implement feature**: Follow test steps exactly
6. **Mark passing**: Use `feature_mark_passing(id)`
7. **Update progress notes**: Write to `claude-progress.txt`
8. **Commit**: Git commit with meaningful message
9. **Auto-continue**: 3-second delay before next session

## Important Design Patterns

### Feature Database Schema

```python
class Feature:
    id: int              # Auto-increment primary key
    priority: int        # Lower = higher priority (assigned by order)
    category: str        # "functional" or "style"
    name: str            # Brief feature name
    description: str     # What this feature/test verifies
    steps: list[str]     # Step-by-step test instructions (JSON array)
    passes: bool         # Implementation status
    in_progress: bool    # Currently being worked on
    failure_count: int   # Consecutive failures (for stuck loop detection)
    last_error: str      # Last error message
    skipped: bool        # Feature was skipped by user request
    approved: bool       # User approved the skip (reviewed)
    skip_reason: str     # Why the feature was skipped
```

### Skip Workflow

When a feature cannot be implemented (dependencies, blockers, user request), use `feature_skip(feature_id, reason)`:

1. **Feature is skipped**: Moves to end of queue, marked `skipped=True`, `approved=False`
2. **Awaiting review**: Skipped features won't be worked on until user approves
3. **User reviews**: Via `./start.sh` menu option "Review skipped features"
4. **Approve or Reject**:
   - **Approve**: Feature re-queued (`skipped=False`, `approved=True`)
   - **Reject**: Feature permanently removed from queue (`skipped=True`, `approved=True`)

**Important**: When you skip a feature, always provide a clear reason so the user understands why it was skipped when they review it.

### Progress Tracking

- `progress.py` uses direct SQLite access (not MCP) for reading stats
- Webhook notifications sent when progress increases (optional N8N integration)
- Progress cached in `.progress_cache` to detect changes

### Authentication

- Uses Claude CLI credentials from `~/.claude/.credentials.json`
- `start.sh`/`start.bat` check authentication before launching
- No API keys in code (handled by SDK auto-detection)

## Modifying the System

### Adding Allowed Bash Commands

Edit `security.py::ALLOWED_COMMANDS`. For commands needing extra validation (like `pkill`, `chmod`), add to `COMMANDS_NEEDING_EXTRA_VALIDATION` and implement validator function.

### Customizing Prompts

**Per-project**: Edit files in `generations/{project}/prompts/`

**System-wide**: Edit templates in `.claude/templates/`

### Changing Feature Count

The feature count target is specified in `app_spec.txt`. Standard tiers:
- Simple apps: ~150 features
- Medium apps: ~250 features
- Complex apps: ~400+ features

### Adding MCP Tools

1. Add tool to MCP server (`mcp_server/feature_mcp.py`)
2. Add to `allowed_tools` in `client.py`
3. Add to permissions in `client.py::create_client()`

## Development Notes

- **Fresh context per session**: Agent has no memory of previous sessions (relies on git, database, progress notes)
- **Auto-continuation**: Sessions automatically chain with 3-second delays (configurable in `agent.py`)
- **Ctrl+C to pause**: Run start script again to resume
- **Projects in `generations/`**: All generated apps stored here
- **Feature-first development**: Features are the atomic unit of work, not tasks
- **One feature per session** (typically): Ensures thorough implementation
- **Regression testing required**: Every session must verify passing features still work

## Troubleshooting

**"Command blocked"**: Command not in `security.py::ALLOWED_COMMANDS` allowlist

**"No features in database"**: Initializer hasn't run or database is empty

**"MCP server not starting"**: Check `PROJECT_DIR` environment variable is set correctly

**Features marked passing incorrectly**: Use SQLite to manually update: `UPDATE features SET passes = 0 WHERE id = X;`

**Session hangs on first run**: Initializer is generating hundreds of features (takes 10-20+ minutes)

**"No available features" but features exist**: Features may be skipped and awaiting user approval. Run `./start.sh` and select "Review skipped features" to approve or reject them.

**Skipped features queries**:
```sql
-- View all skipped features awaiting approval
SELECT id, name, skip_reason FROM features WHERE skipped = 1 AND approved = 0 AND passes = 0;

-- Manually approve a skipped feature
UPDATE features SET skipped = 0, approved = 1, skip_reason = NULL WHERE id = X;

-- Manually reject a skipped feature
UPDATE features SET approved = 1 WHERE id = X AND skipped = 1;
```
