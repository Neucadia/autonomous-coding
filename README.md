# Neucadia Changes
  
Description: Stuck loop detection & failure tracking - Auto-detects repeated failures, tracks per-feature failure counts, auto-skips after 5 failures [1f74b88](https://github.com/Neucadia/autonomous-coding/commit/1f74b88)

Description: Use CLAUDE_CODE_OAUTH_TOKEN in .env file with `claude setup-token`

Description: Add graceful stop functionality for running projects [07e5dc0](https://github.com/Neucadia/autonomous-coding/commit/07e5dc0)

Description: Add in_progress tracking for crash recovery [516768d](https://github.com/Neucadia/autonomous-coding/commit/516768d)

# Autonomous Coding Agent

A long-running autonomous coding agent powered by the Claude Agent SDK. This tool can build complete applications over multiple sessions using a two-agent pattern (initializer + coding agent).

## Video Walkthrough

[![Watch the video](https://img.youtube.com/vi/YW09hhnVqNM/maxresdefault.jpg)](https://youtu.be/YW09hhnVqNM)

> **[Watch the setup and usage guide →](https://youtu.be/YW09hhnVqNM)**

---

## Prerequisites

### Claude Code CLI (Required)

This project requires the Claude Code CLI to be installed. Install it using one of these methods:

**macOS / Linux:**
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://claude.ai/install.ps1 | iex
```

### Authentication

You need one of the following:

- **Claude Pro/Max Subscription** - Use `claude login` to authenticate (recommended)
- **Anthropic API Key** - Pay-per-use from https://console.anthropic.com/

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/your-repo/autonomous-coding.git
cd autonomous-coding
```

### 2. Run the Start Script

**Windows:**
```cmd
start.bat
```

**macOS / Linux:**
```bash
./start.sh
```

The start script will:
1. Check if Claude CLI is installed
2. Check if you're authenticated (prompt to run `claude login` if not)
3. Create a Python virtual environment
4. Install dependencies
5. Launch the main menu

### 3. Create or Continue a Project

You'll see a menu with options to:
- **Create new project** - Start a fresh project with AI-assisted spec generation
- **Continue existing project** - Resume work on a previous project

For new projects, you can use the built-in `/create-spec` command to interactively create your app specification with Claude's help.

---

## How It Works

### Two-Agent Pattern

1. **Initializer Agent (First Session):** Reads your app specification, creates a `feature_list.json` with test cases, sets up the project structure, and initializes git.

2. **Coding Agent (Subsequent Sessions):** Picks up where the previous session left off, implements features one by one, and marks them as passing in `feature_list.json`.

### Session Management

- Each session runs with a fresh context window
- Progress is persisted via `feature_list.json` and git commits
- The agent auto-continues between sessions (3 second delay)
- Press `Ctrl+C` to pause; run the start script again to resume

---

## Important Timing Expectations

> **Note: Building complete applications takes time!**

- **First session (initialization):** The agent generates feature test cases. This takes several minutes and may appear to hang - this is normal.

- **Subsequent sessions:** Each coding iteration can take **5-15 minutes** depending on complexity.

- **Full app:** Building all features typically requires **many hours** of total runtime across multiple sessions.

**Tip:** The feature count in the prompts determines scope. For faster demos, you can modify your app spec to target fewer features (e.g., 20-50 features for a quick demo).

---

## Project Structure

```
autonomous-coding/
├── start.bat                 # Windows start script
├── start.sh                  # macOS/Linux start script
├── start.py                  # Main menu and project management
├── autonomous_agent_demo.py  # Agent entry point
├── agent.py                  # Agent session logic
├── client.py                 # Claude SDK client configuration
├── security.py               # Bash command allowlist and validation
├── progress.py               # Progress tracking utilities
├── prompts.py                # Prompt loading utilities
├── .claude/
│   ├── commands/
│   │   └── create-spec.md    # Interactive spec creation command
│   └── templates/            # Prompt templates
├── generations/              # Generated projects go here
├── requirements.txt          # Python dependencies
└── .env                      # Optional configuration (N8N webhook)
```

---

## Generated Project Structure

After the agent runs, your project directory will contain:

```
generations/my_project/
├── feature_list.json         # Test cases (source of truth)
├── prompts/
│   ├── app_spec.txt          # Your app specification
│   ├── initializer_prompt.md # First session prompt
│   └── coding_prompt.md      # Continuation session prompt
├── init.sh                   # Environment setup script
├── claude-progress.txt       # Session progress notes
└── [application files]       # Generated application code
```

---

## Running the Generated Application

After the agent completes (or pauses), you can run the generated application:

```bash
cd generations/my_project

# Run the setup script created by the agent
./init.sh

# Or manually (typical for Node.js apps):
npm install
npm run dev
```

The application will typically be available at `http://localhost:3000` or similar.

---

## Security Model

This project uses a defense-in-depth security approach (see `security.py` and `client.py`):

1. **OS-level Sandbox:** Bash commands run in an isolated environment
2. **Filesystem Restrictions:** File operations restricted to the project directory only
3. **Bash Allowlist:** Only specific commands are permitted:
   - File inspection: `ls`, `cat`, `head`, `tail`, `wc`, `grep`
   - Node.js: `npm`, `node`
   - Version control: `git`
   - Process management: `ps`, `lsof`, `sleep`, `pkill` (dev processes only)

Commands not in the allowlist are blocked by the security hook.

---

## Configuration (Optional)

### N8N Webhook Integration

The agent can send progress notifications to an N8N webhook. Create a `.env` file:

```bash
# Optional: N8N webhook for progress notifications
PROGRESS_N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/your-webhook-id
```

When test progress increases, the agent sends:

```json
{
  "event": "test_progress",
  "passing": 45,
  "total": 200,
  "percentage": 22.5,
  "project": "my_project",
  "timestamp": "2025-01-15T14:30:00.000Z"
}
```

---

## Customization

### Changing the Application

Use the `/create-spec` command when creating a new project, or manually edit the files in your project's `prompts/` directory:
- `app_spec.txt` - Your application specification
- `initializer_prompt.md` - Controls feature generation

### Modifying Allowed Commands

Edit `security.py` to add or remove commands from `ALLOWED_COMMANDS`.

---

## Troubleshooting

**"Claude CLI not found"**
Install the Claude Code CLI using the instructions in the Prerequisites section.

**"Not authenticated with Claude"**
Run `claude login` to authenticate. The start script will prompt you to do this automatically.

**"Appears to hang on first run"**
This is normal. The initializer agent is generating detailed test cases, which takes significant time. Watch for `[Tool: ...]` output to confirm the agent is working.

**"Command blocked by security hook"**
The agent tried to run a command not in the allowlist. This is the security system working as intended. If needed, add the command to `ALLOWED_COMMANDS` in `security.py`.

---

## License

Internal Anthropic use.
