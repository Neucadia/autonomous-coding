#!/usr/bin/env python3
"""
Simple CLI launcher for the Autonomous Coding Agent.
Provides an interactive menu to create new projects or continue existing ones.

Supports two paths for new projects:
1. Claude path: Use /create-spec to generate spec interactively
2. Manual path: Edit template files directly, then continue
"""

import asyncio
import os
import sys
import subprocess
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file (if it exists)
load_dotenv()

from prompts import (
    scaffold_project_prompts,
    has_project_prompts,
    get_project_prompts_dir,
)
from agent import request_stop, run_add_features_session
from progress import has_features


# Directory containing generated projects
GENERATIONS_DIR = Path(__file__).parent / "generations"


def check_spec_exists(project_dir: Path) -> bool:
    """
    Check if valid spec files exist for a project.

    Checks in order:
    1. Project prompts directory: {project_dir}/prompts/app_spec.txt
    2. Project root (legacy): {project_dir}/app_spec.txt
    """
    # Check project prompts directory first
    project_prompts = get_project_prompts_dir(project_dir)
    spec_file = project_prompts / "app_spec.txt"
    if spec_file.exists():
        try:
            content = spec_file.read_text(encoding="utf-8")
            return "<project_specification>" in content
        except (OSError, PermissionError):
            return False

    # Check legacy location in project root
    legacy_spec = project_dir / "app_spec.txt"
    if legacy_spec.exists():
        try:
            content = legacy_spec.read_text(encoding="utf-8")
            return "<project_specification>" in content
        except (OSError, PermissionError):
            return False

    return False


def get_existing_projects() -> list[str]:
    """Get list of existing projects from generations folder."""
    if not GENERATIONS_DIR.exists():
        return []

    projects = []
    for item in GENERATIONS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            projects.append(item.name)

    return sorted(projects)


def display_menu(projects: list[str]) -> None:
    """Display the main menu."""
    print("\n" + "=" * 50)
    print("  Autonomous Coding Agent Launcher")
    print("=" * 50)
    print("\n[1] Create new project")

    if projects:
        print("[2] Continue existing project")
        print("[3] Add new features to existing project")
        print("[4] Stop running project (graceful)")

    print("[q] Quit")
    print()


def display_projects(projects: list[str]) -> None:
    """Display list of existing projects."""
    print("\n" + "-" * 40)
    print("  Existing Projects")
    print("-" * 40)

    for i, project in enumerate(projects, 1):
        print(f"  [{i}] {project}")

    print("\n  [b] Back to main menu")
    print()


def get_project_choice(projects: list[str]) -> str | None:
    """Get user's project selection."""
    while True:
        choice = input("Select project number: ").strip().lower()

        if choice == 'b':
            return None

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(projects):
                return projects[idx]
            print(f"Please enter a number between 1 and {len(projects)}")
        except ValueError:
            print("Invalid input. Enter a number or 'b' to go back.")


def get_new_project_name() -> str | None:
    """Get name for new project."""
    print("\n" + "-" * 40)
    print("  Create New Project")
    print("-" * 40)
    print("\nEnter project name (e.g., my-awesome-app)")
    print("Leave empty to cancel.\n")

    name = input("Project name: ").strip()

    if not name:
        return None

    # Basic validation - OS-aware invalid characters
    # Windows has more restrictions than Unix
    if sys.platform == "win32":
        invalid_chars = '<>:"/\\|?*'
    else:
        # Unix only restricts / and null
        invalid_chars = '/'

    for char in invalid_chars:
        if char in name:
            print(f"Invalid character '{char}' in project name")
            return None

    return name


def ensure_project_scaffolded(project_name: str) -> Path:
    """
    Ensure project directory exists with prompt templates.

    Creates the project directory and copies template files if needed.

    Returns:
        The project directory path
    """
    project_dir = GENERATIONS_DIR / project_name

    # Create project directory if it doesn't exist
    project_dir.mkdir(parents=True, exist_ok=True)

    # Scaffold prompts (copies templates if they don't exist)
    print(f"\nSetting up project: {project_name}")
    scaffold_project_prompts(project_dir)

    return project_dir


def run_spec_creation(project_dir: Path) -> bool:
    """
    Run Claude Code with /create-spec command to create project specification.

    The project path is passed as an argument so create-spec knows where to write files.
    """
    print("\n" + "=" * 50)
    print("  Project Specification Setup")
    print("=" * 50)
    print(f"\nProject directory: {project_dir}")
    print(f"Prompts will be saved to: {get_project_prompts_dir(project_dir)}")
    print("\nLaunching Claude Code for interactive spec creation...")
    print("Answer the questions to define your project.")
    print("When done, Claude will generate the spec files.")
    print("Exit Claude Code (Ctrl+C or /exit) when finished.\n")

    try:
        # Launch Claude Code with /create-spec command
        # Project path included in command string so it populates $ARGUMENTS
        subprocess.run(
            ["claude", f"/create-spec {project_dir}"],
            check=False,  # Don't raise on non-zero exit
            cwd=str(Path(__file__).parent)  # Run from project root
        )

        # Check if spec was created in project prompts directory
        if check_spec_exists(project_dir):
            print("\n" + "-" * 50)
            print("Spec files created successfully!")
            return True
        else:
            print("\n" + "-" * 50)
            print("Spec creation incomplete.")
            print(f"Please ensure app_spec.txt exists in: {get_project_prompts_dir(project_dir)}")
            return False

    except FileNotFoundError:
        print("\nError: 'claude' command not found.")
        print("Make sure Claude Code CLI is installed:")
        print("  npm install -g @anthropic-ai/claude-code")
        return False
    except KeyboardInterrupt:
        print("\n\nSpec creation cancelled.")
        return False


def run_manual_spec_flow(project_dir: Path) -> bool:
    """
    Guide user through manual spec editing flow.

    Shows the paths to edit and waits for user to press Enter when ready.
    """
    prompts_dir = get_project_prompts_dir(project_dir)

    print("\n" + "-" * 50)
    print("  Manual Specification Setup")
    print("-" * 50)
    print("\nTemplate files have been created. Edit these files in your editor:")
    print(f"\n  Required:")
    print(f"    {prompts_dir / 'app_spec.txt'}")
    print(f"\n  Optional (customize agent behavior):")
    print(f"    {prompts_dir / 'initializer_prompt.md'}")
    print(f"    {prompts_dir / 'coding_prompt.md'}")
    print("\n" + "-" * 50)
    print("\nThe app_spec.txt file contains a template with placeholders.")
    print("Replace the placeholders with your actual project specification.")
    print("\nWhen you're done editing, press Enter to continue...")

    try:
        input()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        return False

    # Validate that spec was edited
    if check_spec_exists(project_dir):
        print("\nSpec file validated successfully!")
        return True
    else:
        print("\nWarning: The app_spec.txt file still contains the template placeholder.")
        print("The agent may not work correctly without a proper specification.")
        confirm = input("Continue anyway? [y/N]: ").strip().lower()
        return confirm == 'y'


def ask_spec_creation_choice() -> str | None:
    """Ask user whether to create spec with Claude or manually."""
    print("\n" + "-" * 40)
    print("  Specification Setup")
    print("-" * 40)
    print("\nHow would you like to define your project?")
    print("\n[1] Create spec with Claude (recommended)")
    print("    Interactive conversation to define your project")
    print("\n[2] Edit templates manually")
    print("    Edit the template files directly in your editor")
    print("\n[b] Back to main menu")
    print()

    while True:
        choice = input("Select [1/2/b]: ").strip().lower()
        if choice in ['1', '2', 'b']:
            return choice
        print("Invalid choice. Please enter 1, 2, or b.")


def create_new_project_flow() -> str | None:
    """
    Complete flow for creating a new project.

    1. Get project name
    2. Create project directory and scaffold prompts
    3. Ask: Claude or Manual?
    4. If Claude: Run /create-spec with project path
    5. If Manual: Show paths, wait for Enter
    6. Return project name if successful
    """
    project_name = get_new_project_name()
    if not project_name:
        return None

    # Create project directory and scaffold prompts FIRST
    project_dir = ensure_project_scaffolded(project_name)

    # Ask user how they want to handle spec creation
    choice = ask_spec_creation_choice()

    if choice == 'b':
        return None
    elif choice == '1':
        # Create spec with Claude
        success = run_spec_creation(project_dir)
        if not success:
            print("\nYou can try again later or edit the templates manually.")
            retry = input("Start agent anyway? [y/N]: ").strip().lower()
            if retry != 'y':
                return None
    elif choice == '2':
        # Manual mode - guide user through editing
        success = run_manual_spec_flow(project_dir)
        if not success:
            return None

    return project_name


def stop_project_flow(projects: list[str]) -> None:
    """
    Flow for requesting a graceful stop of a running project.

    Shows the project list and creates a stop file for the selected project.
    The running agent will stop after completing its current feature.
    """
    print("\n" + "-" * 40)
    print("  Stop Running Project")
    print("-" * 40)
    print("\nSelect a project to stop. The agent will finish")
    print("its current feature before stopping.\n")

    for i, project in enumerate(projects, 1):
        print(f"  [{i}] {project}")

    print("\n  [b] Back to main menu")
    print()

    while True:
        choice = input("Select project number: ").strip().lower()

        if choice == 'b':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(projects):
                project_name = projects[idx]
                project_dir = GENERATIONS_DIR / project_name
                request_stop(project_dir)
                print()
                return
            print(f"Please enter a number between 1 and {len(projects)}")
        except ValueError:
            print("Invalid input. Enter a number or 'b' to go back.")


def get_feature_count() -> int | None:
    """Ask user how many features to add."""
    print("\nHow many features would you like to add?")
    print("(Press Enter for default of 15, or enter a number)")
    print()

    while True:
        choice = input("Feature count [15]: ").strip()

        if choice == '':
            return 15

        try:
            count = int(choice)
            if count < 1:
                print("Please enter a positive number.")
                continue
            if count > 100:
                confirm = input(f"Add {count} features? That's a lot! [y/N]: ").strip().lower()
                if confirm != 'y':
                    continue
            return count
        except ValueError:
            print("Invalid input. Enter a number or press Enter for default.")


def get_feature_description() -> str | None:
    """Ask user for a description of what features to add."""
    print("\n" + "-" * 40)
    print("  Describe Features to Add")
    print("-" * 40)
    print("\nDescribe what features you want to add.")
    print("Be specific about the functionality, pages, or behaviors.")
    print("\nExamples:")
    print("  - Add user authentication with login, logout, and password reset")
    print("  - Add a dashboard with charts showing sales data")
    print("  - Add form validation for all input fields")
    print("\nEnter your description (or 'b' to go back):")
    print()

    lines = []
    print("(Enter an empty line when done)")
    while True:
        try:
            line = input()
            if line.strip().lower() == 'b' and not lines:
                return None
            if line == '' and lines:
                break
            lines.append(line)
        except KeyboardInterrupt:
            print("\n\nCancelled.")
            return None

    description = '\n'.join(lines).strip()
    if not description:
        print("No description provided.")
        return None

    return description


def add_features_flow(projects: list[str]) -> None:
    """
    Flow for adding new features to an existing project.

    Shows the project list, asks for feature count, and runs the add features agent.
    """
    print("\n" + "-" * 40)
    print("  Add New Features to Existing Project")
    print("-" * 40)
    print("\nSelect a project to add features to.\n")

    # Filter to only show projects with existing features
    projects_with_features = []
    for project in projects:
        project_dir = GENERATIONS_DIR / project
        if has_features(project_dir):
            projects_with_features.append(project)

    if not projects_with_features:
        print("No projects with existing features found.")
        print("Use 'Continue existing project' first to initialize features.")
        input("\nPress Enter to continue...")
        return

    for i, project in enumerate(projects_with_features, 1):
        print(f"  [{i}] {project}")

    print("\n  [b] Back to main menu")
    print()

    while True:
        choice = input("Select project number: ").strip().lower()

        if choice == 'b':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(projects_with_features):
                project_name = projects_with_features[idx]
                break
            print(f"Please enter a number between 1 and {len(projects_with_features)}")
        except ValueError:
            print("Invalid input. Enter a number or 'b' to go back.")

    # Ask for feature description first
    feature_description = get_feature_description()
    if feature_description is None:
        return

    # Ask for feature count
    feature_count = get_feature_count()
    if feature_count is None:
        return

    # Run add features session
    project_dir = GENERATIONS_DIR / project_name
    run_add_features(project_name, feature_count, feature_description)


def run_add_features(project_name: str, feature_count: int, feature_description: str) -> None:
    """Run the add features agent session for a project."""
    project_dir = GENERATIONS_DIR / project_name

    print(f"\nAdding {feature_count} features to project: {project_name}")
    print("-" * 50)
    print(f"\nFeature description:\n{feature_description}")
    print("-" * 50)

    # Default model (same as autonomous_agent_demo.py)
    model = "claude-opus-4-5-20251101"

    try:
        asyncio.run(
            run_add_features_session(
                project_dir=project_dir,
                model=model,
                feature_count=feature_count,
                feature_description=feature_description,
            )
        )
    except KeyboardInterrupt:
        print("\n\nAdd features interrupted.")
    except Exception as e:
        print(f"\nError adding features: {e}")


def run_agent(project_name: str) -> None:
    """Run the autonomous agent with the given project."""
    project_dir = GENERATIONS_DIR / project_name

    # Final validation before running
    if not has_project_prompts(project_dir):
        print(f"\nWarning: No valid spec found for project '{project_name}'")
        print("The agent may not work correctly.")
        confirm = input("Continue anyway? [y/N]: ").strip().lower()
        if confirm != 'y':
            return

    print(f"\nStarting agent for project: {project_name}")
    print("-" * 50)

    # Build the command
    cmd = [sys.executable, "autonomous_agent_demo.py", "--project-dir", project_name]

    # Run the agent
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        print("\n\nAgent interrupted. Run again to resume.")


def main() -> None:
    """Main entry point."""
    # Ensure we're in the right directory
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)

    while True:
        projects = get_existing_projects()
        display_menu(projects)

        choice = input("Select option: ").strip().lower()

        if choice == 'q':
            print("\nGoodbye!")
            break

        elif choice == '1':
            project_name = create_new_project_flow()
            if project_name:
                run_agent(project_name)

        elif choice == '2' and projects:
            display_projects(projects)
            selected = get_project_choice(projects)
            if selected:
                run_agent(selected)

        elif choice == '3' and projects:
            add_features_flow(projects)

        elif choice == '4' and projects:
            stop_project_flow(projects)

        else:
            print("Invalid option. Please try again.")


if __name__ == "__main__":
    main()
