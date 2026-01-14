"""
Claude SDK Client Configuration
===============================

Functions for creating and configuring the Claude Agent SDK client.
"""

import json
import os
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import HookMatcher

from security import bash_security_hook


# Feature MCP tools for feature/test management
FEATURE_MCP_TOOLS = [
    "mcp__features__feature_get_stats",
    "mcp__features__feature_get_next",
    "mcp__features__feature_get_for_regression",
    "mcp__features__feature_mark_passing",
    "mcp__features__feature_skip",
    "mcp__features__feature_create_bulk",
    "mcp__features__feature_record_failure",  # For stuck loop recovery
]

# Expo MCP tools for React Native/Expo development
EXPO_MCP_TOOLS = [
    # Remote capabilities (documentation & package management)
    "mcp__expo__learn",
    "mcp__expo__search_documentation",
    "mcp__expo__add_library",
    "mcp__expo__generate_claude_md",
    "mcp__expo__generate_agents_md",

    # Local capabilities (requires local dev server with expo-mcp)
    "mcp__expo__expo_router_sitemap",
    "mcp__expo__open_devtools",
    "mcp__expo__automation_tap",
    "mcp__expo__automation_take_screenshot",
    "mcp__expo__automation_find_view_by_testid",
    "mcp__expo__automation_tap_by_testid",
    "mcp__expo__automation_take_screenshot_by_testid",
]

# Playwright MCP tools for browser automation
PLAYWRIGHT_TOOLS = [
    # Core navigation & screenshots
    "mcp__playwright__browser_navigate",
    "mcp__playwright__browser_navigate_back",
    "mcp__playwright__browser_take_screenshot",
    "mcp__playwright__browser_snapshot",

    # Element interaction
    "mcp__playwright__browser_click",
    "mcp__playwright__browser_type",
    "mcp__playwright__browser_fill_form",
    "mcp__playwright__browser_select_option",
    "mcp__playwright__browser_hover",
    "mcp__playwright__browser_drag",
    "mcp__playwright__browser_press_key",

    # JavaScript & debugging
    "mcp__playwright__browser_evaluate",
    "mcp__playwright__browser_run_code",
    "mcp__playwright__browser_console_messages",
    "mcp__playwright__browser_network_requests",

    # Browser management
    "mcp__playwright__browser_close",
    "mcp__playwright__browser_resize",
    "mcp__playwright__browser_tabs",
    "mcp__playwright__browser_wait_for",
    "mcp__playwright__browser_handle_dialog",
    "mcp__playwright__browser_file_upload",
    "mcp__playwright__browser_install",
]

# Built-in tools
BUILTIN_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
]


def create_client(project_dir: Path, model: str):
    """
    Create a Claude Agent SDK client with multi-layered security.

    Args:
        project_dir: Directory for the project
        model: Claude model to use

    Returns:
        Configured ClaudeSDKClient (from claude_agent_sdk)

    Security layers (defense in depth):
    1. Sandbox - OS-level bash command isolation prevents filesystem escape
    2. Permissions - File operations restricted to project_dir only
    3. Security hooks - Bash commands validated against an allowlist
       (see security.py for ALLOWED_COMMANDS)

    Note: Authentication is handled by start.bat/start.sh before this runs.
    The Claude SDK auto-detects credentials from ~/.claude/.credentials.json
    """
    # Create comprehensive security settings
    # Note: Using relative paths ("./**") restricts access to project directory
    # since cwd is set to project_dir
    security_settings = {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
        "permissions": {
            "defaultMode": "acceptEdits",  # Auto-approve edits within allowed directories
            "allow": [
                # Allow all file operations within the project directory
                "Read(./**)",
                "Write(./**)",
                "Edit(./**)",
                "Glob(./**)",
                "Grep(./**)",
                # Bash permission granted here, but actual commands are validated
                # by the bash_security_hook (see security.py for allowed commands)
                "Bash(*)",
                # Allow Playwright MCP tools for browser automation
                *PLAYWRIGHT_TOOLS,
                # Allow Feature MCP tools for feature management
                *FEATURE_MCP_TOOLS,
                # Allow Expo MCP tools for React Native/Expo development
                *EXPO_MCP_TOOLS,
            ],
        },
    }

    # Ensure project directory exists before creating settings file
    project_dir.mkdir(parents=True, exist_ok=True)

    # Write settings to a file in the project directory
    settings_file = project_dir / ".claude_settings.json"
    with open(settings_file, "w") as f:
        json.dump(security_settings, f, indent=2)

    print(f"Created security settings at {settings_file}")
    print("   - Sandbox enabled (OS-level bash isolation)")
    print(f"   - Filesystem restricted to: {project_dir.resolve()}")
    print("   - Bash commands restricted to allowlist (see security.py)")
    print("   - MCP servers: playwright (browser), features (database), expo (React Native)")
    print("   - Project settings enabled (skills, commands, CLAUDE.md)")
    print()

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt="You are an expert full-stack developer building a production-quality web application.",
            setting_sources=["project"],  # Enable skills, commands, and CLAUDE.md from project dir
            max_buffer_size=10 * 1024 * 1024,  # 10MB for large Playwright screenshots
            allowed_tools=[
                *BUILTIN_TOOLS,
                *PLAYWRIGHT_TOOLS,
                *FEATURE_MCP_TOOLS,
                *EXPO_MCP_TOOLS,
            ],
            mcp_servers={
                "playwright": {"command": "npx", "args": ["@playwright/mcp@latest", "--viewport-size", "1280x720"]},
                # "playwright": {"command": "npx", "args": ["@playwright/mcp@latest", "--headless"]},
                "features": {
                    "command": sys.executable,  # Use the same Python that's running this script
                    "args": ["-m", "mcp_server.feature_mcp"],
                    "env": {
                        "PROJECT_DIR": str(project_dir.resolve()),
                        "PYTHONPATH": str(Path(__file__).parent.resolve()),
                    },
                },
                "expo": {
                    "command": "npx",
                    "args": ["@anthropic-ai/claude-mcp-server-expo"],
                    "env": {
                        # Enable local capabilities for automation (screenshots, taps, etc.)
                        "EXPO_UNSTABLE_MCP_SERVER": "1",
                    },
                },
            },
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
                ],
            },
            max_turns=1000,
            cwd=str(project_dir.resolve()),
            settings=str(settings_file.resolve()),  # Use absolute path
        )
    )
