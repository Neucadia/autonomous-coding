"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Uses direct SQLite access for database queries.
"""

import json
import os
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path


WEBHOOK_URL = os.environ.get("PROGRESS_N8N_WEBHOOK_URL")
PROGRESS_CACHE_FILE = ".progress_cache"


def has_features(project_dir: Path) -> bool:
    """
    Check if the project has features in the database.

    This is used to determine if the initializer agent needs to run.
    We check the database directly (not via API) since the API server
    may not be running yet when this check is performed.

    Returns True if:
    - features.db exists AND has at least 1 feature, OR
    - feature_list.json exists (legacy format)

    Returns False if no features exist (initializer needs to run).
    """
    import sqlite3

    # Check legacy JSON file first
    json_file = project_dir / "feature_list.json"
    if json_file.exists():
        return True

    # Check SQLite database
    db_file = project_dir / "features.db"
    if not db_file.exists():
        return False

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM features")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        # Database exists but can't be read or has no features table
        return False


def count_passing_tests(project_dir: Path) -> tuple[int, int]:
    """
    Count passing and total tests via direct database access.

    Args:
        project_dir: Directory containing the project

    Returns:
        (passing_count, total_count)
    """
    db_file = project_dir / "features.db"
    if not db_file.exists():
        return 0, 0

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM features")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM features WHERE passes = 1")
        passing = cursor.fetchone()[0]
        conn.close()
        return passing, total
    except Exception as e:
        print(f"[Database error in count_passing_tests: {e}]")
        return 0, 0


def get_all_passing_features(project_dir: Path) -> list[dict]:
    """
    Get all passing features for webhook notifications.

    Args:
        project_dir: Directory containing the project

    Returns:
        List of dicts with id, category, name for each passing feature
    """
    db_file = project_dir / "features.db"
    if not db_file.exists():
        return []

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, category, name FROM features WHERE passes = 1 ORDER BY priority ASC"
        )
        features = [
            {"id": row[0], "category": row[1], "name": row[2]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return features
    except Exception:
        return []


def send_progress_webhook(passing: int, total: int, project_dir: Path) -> None:
    """Send webhook notification when progress increases."""
    if not WEBHOOK_URL:
        return  # Webhook not configured

    cache_file = project_dir / PROGRESS_CACHE_FILE
    previous = 0
    previous_passing_ids = set()

    # Read previous progress and passing feature IDs
    if cache_file.exists():
        try:
            cache_data = json.loads(cache_file.read_text())
            previous = cache_data.get("count", 0)
            previous_passing_ids = set(cache_data.get("passing_ids", []))
        except Exception:
            previous = 0

    # Only notify if progress increased
    if passing > previous:
        # Find which features are now passing via API
        completed_tests = []
        current_passing_ids = []

        # Detect transition from old cache format (had count but no passing_ids)
        # In this case, we can't reliably identify which specific tests are new
        is_old_cache_format = len(previous_passing_ids) == 0 and previous > 0

        # Get all passing features via direct database access
        all_passing = get_all_passing_features(project_dir)
        for feature in all_passing:
            feature_id = feature.get("id")
            current_passing_ids.append(feature_id)
            # Only identify individual new tests if we have previous IDs to compare
            if not is_old_cache_format and feature_id not in previous_passing_ids:
                # This feature is newly passing
                name = feature.get("name", f"Feature #{feature_id}")
                category = feature.get("category", "")
                if category:
                    completed_tests.append(f"{category} {name}")
                else:
                    completed_tests.append(name)

        payload = {
            "event": "test_progress",
            "passing": passing,
            "total": total,
            "percentage": round((passing / total) * 100, 1) if total > 0 else 0,
            "previous_passing": previous,
            "tests_completed_this_session": passing - previous,
            "completed_tests": completed_tests,
            "project": project_dir.name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        try:
            req = urllib.request.Request(
                WEBHOOK_URL,
                data=json.dumps([payload]).encode("utf-8"),  # n8n expects array
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"[Webhook notification failed: {e}]")

        # Update cache with count and passing IDs
        cache_file.write_text(
            json.dumps({"count": passing, "passing_ids": current_passing_ids})
        )
    else:
        # Update cache even if no change (for initial state)
        if not cache_file.exists():
            all_passing = get_all_passing_features(project_dir)
            current_passing_ids = [f.get("id") for f in all_passing]
            cache_file.write_text(
                json.dumps({"count": passing, "passing_ids": current_passing_ids})
            )


def print_session_header(session_num: int, is_initializer: bool) -> None:
    """Print a formatted header for the session."""
    session_type = "INITIALIZER" if is_initializer else "CODING AGENT"

    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {session_type}")
    print("=" * 70)
    print()


def print_progress_summary(project_dir: Path) -> None:
    """Print a summary of current progress."""
    passing, total = count_passing_tests(project_dir)

    if total > 0:
        percentage = (passing / total) * 100
        print(f"\nProgress: {passing}/{total} tests passing ({percentage:.1f}%)")
        send_progress_webhook(passing, total, project_dir)
    else:
        print("\nProgress: No features in database yet")


def get_skipped_features(project_dir: Path) -> list[dict]:
    """
    Get all features that are skipped and awaiting approval.

    Args:
        project_dir: Directory containing the project

    Returns:
        List of dicts with feature details for skipped features
    """
    db_file = project_dir / "features.db"
    if not db_file.exists():
        return []

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        # Check if skipped column exists
        cursor.execute("PRAGMA table_info(features)")
        columns = [row[1] for row in cursor.fetchall()]
        if "skipped" not in columns:
            conn.close()
            return []

        cursor.execute(
            """SELECT id, priority, category, name, description, skip_reason
               FROM features
               WHERE skipped = 1 AND (approved = 0 OR approved IS NULL) AND passes = 0
               ORDER BY priority ASC"""
        )
        features = [
            {
                "id": row[0],
                "priority": row[1],
                "category": row[2],
                "name": row[3],
                "description": row[4],
                "skip_reason": row[5],
            }
            for row in cursor.fetchall()
        ]
        conn.close()
        return features
    except Exception as e:
        print(f"[Database error in get_skipped_features: {e}]")
        return []


def approve_skipped_feature(project_dir: Path, feature_id: int) -> bool:
    """
    Approve a skipped feature, allowing it to be worked on again.

    Args:
        project_dir: Directory containing the project
        feature_id: The ID of the feature to approve

    Returns:
        True if successful, False otherwise
    """
    db_file = project_dir / "features.db"
    if not db_file.exists():
        return False

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE features
               SET skipped = 0, approved = 1, skip_reason = NULL
               WHERE id = ?""",
            (feature_id,)
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        print(f"[Database error in approve_skipped_feature: {e}]")
        return False


def reject_skipped_feature(project_dir: Path, feature_id: int) -> bool:
    """
    Reject a skipped feature, permanently removing it from the queue.

    The feature stays marked as skipped but is also marked as approved
    (reviewed), meaning it won't appear in the approval queue or the
    pending features.

    Args:
        project_dir: Directory containing the project
        feature_id: The ID of the feature to reject

    Returns:
        True if successful, False otherwise
    """
    db_file = project_dir / "features.db"
    if not db_file.exists():
        return False

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE features
               SET approved = 1
               WHERE id = ? AND skipped = 1""",
            (feature_id,)
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        print(f"[Database error in reject_skipped_feature: {e}]")
        return False


def count_skipped_features(project_dir: Path) -> int:
    """
    Count features that are skipped and awaiting approval.

    Args:
        project_dir: Directory containing the project

    Returns:
        Number of skipped features awaiting approval
    """
    db_file = project_dir / "features.db"
    if not db_file.exists():
        return 0

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        # Check if skipped column exists
        cursor.execute("PRAGMA table_info(features)")
        columns = [row[1] for row in cursor.fetchall()]
        if "skipped" not in columns:
            conn.close()
            return 0

        cursor.execute(
            """SELECT COUNT(*) FROM features
               WHERE skipped = 1 AND (approved = 0 OR approved IS NULL) AND passes = 0"""
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0
