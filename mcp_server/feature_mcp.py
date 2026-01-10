#!/usr/bin/env python3
"""
MCP Server for Feature Management
==================================

Provides tools to manage features in the autonomous coding system,
replacing the previous FastAPI-based REST API.

Tools:
- feature_get_stats: Get progress statistics
- feature_get_next: Get next feature to implement
- feature_get_for_regression: Get random passing features for testing
- feature_mark_passing: Mark a feature as passing
- feature_skip: Skip a feature (move to end of queue)
- feature_create_bulk: Create multiple features at once
"""

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from sqlalchemy.sql.expression import func

# Add parent directory to path so we can import from api module
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Feature, create_database
from api.migration import (
    migrate_json_to_sqlite,
    migrate_add_in_progress_column,
    migrate_add_failure_tracking_columns,
)

# Maximum consecutive failures before auto-skipping a feature
MAX_FEATURE_FAILURES = 5

# Configuration from environment
PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", ".")).resolve()


# Pydantic models for input validation
class MarkPassingInput(BaseModel):
    """Input for marking a feature as passing."""
    feature_id: int = Field(..., description="The ID of the feature to mark as passing", ge=1)


class SkipFeatureInput(BaseModel):
    """Input for skipping a feature."""
    feature_id: int = Field(..., description="The ID of the feature to skip", ge=1)


class RegressionInput(BaseModel):
    """Input for getting regression features."""
    limit: int = Field(default=3, ge=1, le=10, description="Maximum number of passing features to return")


class FeatureCreateItem(BaseModel):
    """Schema for creating a single feature."""
    category: str = Field(..., min_length=1, max_length=100, description="Feature category")
    name: str = Field(..., min_length=1, max_length=255, description="Feature name")
    description: str = Field(..., min_length=1, description="Detailed description")
    steps: list[str] = Field(..., min_length=1, description="Implementation/test steps")


class BulkCreateInput(BaseModel):
    """Input for bulk creating features."""
    features: list[FeatureCreateItem] = Field(..., min_length=1, description="List of features to create")


# Global database session maker (initialized on startup)
_session_maker = None
_engine = None


@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Initialize database on startup, cleanup on shutdown."""
    global _session_maker, _engine

    # Create project directory if it doesn't exist
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database
    _engine, _session_maker = create_database(PROJECT_DIR)

    # Run migrations
    migrate_json_to_sqlite(PROJECT_DIR, _session_maker)  # Legacy JSON to SQLite
    migrate_add_in_progress_column(PROJECT_DIR, _session_maker)  # Add in_progress column
    migrate_add_failure_tracking_columns(PROJECT_DIR, _session_maker)  # Add failure tracking

    yield

    # Cleanup
    if _engine:
        _engine.dispose()


# Initialize the MCP server
mcp = FastMCP("features", lifespan=server_lifespan)


def get_session():
    """Get a new database session."""
    if _session_maker is None:
        raise RuntimeError("Database not initialized")
    return _session_maker()


@mcp.tool()
def feature_get_stats() -> str:
    """Get statistics about feature completion progress.

    Returns the number of passing features, total features, and completion percentage.
    Use this to track overall progress of the implementation.

    Returns:
        JSON with: passing (int), total (int), percentage (float)
    """
    session = get_session()
    try:
        total = session.query(Feature).count()
        passing = session.query(Feature).filter(Feature.passes == True).count()
        percentage = round((passing / total) * 100, 1) if total > 0 else 0.0

        return json.dumps({
            "passing": passing,
            "total": total,
            "percentage": percentage
        }, indent=2)
    finally:
        session.close()


@mcp.tool()
def feature_get_next() -> str:
    """Get the highest-priority pending feature to work on.

    If a feature is already marked as in_progress (from a previous crashed session),
    returns that feature to allow resuming interrupted work.

    Otherwise, returns the feature with the lowest priority number that has passes=false
    and marks it as in_progress.

    Features that have failed too many times (failure_count >= 5) are automatically
    skipped and moved to the end of the queue.

    Returns:
        JSON with feature details (id, priority, category, name, description, steps, passes, in_progress, failure_count, last_error)
        or error message if all features are passing.
        If resuming, includes "resumed": true and a message.
        If feature has previous failures, includes "attempts_remaining" count.
    """
    session = get_session()
    try:
        # First, check for any in-progress feature (resume interrupted work)
        in_progress_feature = (
            session.query(Feature)
            .filter(Feature.in_progress == True)
            .first()
        )

        if in_progress_feature:
            # Check if this feature has exceeded failure threshold
            failure_count = in_progress_feature.failure_count or 0
            if failure_count >= MAX_FEATURE_FAILURES:
                # Auto-skip this problematic feature
                max_priority_result = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
                new_priority = (max_priority_result[0] + 1) if max_priority_result else 1
                old_priority = in_progress_feature.priority
                in_progress_feature.priority = new_priority
                in_progress_feature.in_progress = False
                in_progress_feature.failure_count = 0  # Reset for future attempts
                session.commit()

                # Get the next feature instead
                return json.dumps({
                    "auto_skipped": True,
                    "skipped_feature_id": in_progress_feature.id,
                    "skipped_feature_name": in_progress_feature.name,
                    "reason": f"Feature failed {failure_count} times consecutively and was auto-skipped",
                    "last_error": in_progress_feature.last_error,
                    "message": "Fetching next feature..."
                }, indent=2)

            return json.dumps({
                **in_progress_feature.to_dict(),
                "resumed": True,
                "message": "Resuming previously started feature",
                "attempts_remaining": MAX_FEATURE_FAILURES - failure_count,
            }, indent=2)

        # Get next pending feature by priority (skip features with too many failures)
        feature = (
            session.query(Feature)
            .filter(Feature.passes == False)
            .filter((Feature.failure_count == None) | (Feature.failure_count < MAX_FEATURE_FAILURES))
            .order_by(Feature.priority.asc(), Feature.id.asc())
            .first()
        )

        if feature is None:
            # Check if there are any features that were skipped due to failures
            failed_features = (
                session.query(Feature)
                .filter(Feature.passes == False)
                .filter(Feature.failure_count >= MAX_FEATURE_FAILURES)
                .count()
            )
            if failed_features > 0:
                return json.dumps({
                    "error": f"All remaining features have failed too many times ({failed_features} features blocked). Manual intervention required.",
                    "blocked_count": failed_features
                })
            return json.dumps({"error": "All features are passing! No more work to do."})

        # Mark as in_progress
        feature.in_progress = True
        session.commit()
        session.refresh(feature)

        result = feature.to_dict()
        failure_count = feature.failure_count or 0
        if failure_count > 0:
            result["attempts_remaining"] = MAX_FEATURE_FAILURES - failure_count
            result["warning"] = f"This feature has failed {failure_count} time(s) previously"

        return json.dumps(result, indent=2)
    finally:
        session.close()


@mcp.tool()
def feature_get_for_regression(
    limit: Annotated[int, Field(default=3, ge=1, le=10, description="Maximum number of passing features to return")] = 3
) -> str:
    """Get random passing features for regression testing.

    Returns a random selection of features that are currently passing.
    Use this to verify that previously implemented features still work
    after making changes.

    Args:
        limit: Maximum number of features to return (1-10, default 3)

    Returns:
        JSON with: features (list of feature objects), count (int)
    """
    session = get_session()
    try:
        features = (
            session.query(Feature)
            .filter(Feature.passes == True)
            .order_by(func.random())
            .limit(limit)
            .all()
        )

        return json.dumps({
            "features": [f.to_dict() for f in features],
            "count": len(features)
        }, indent=2)
    finally:
        session.close()


@mcp.tool()
def feature_mark_passing(
    feature_id: Annotated[int, Field(description="The ID of the feature to mark as passing", ge=1)]
) -> str:
    """Mark a feature as passing after successful implementation.

    Updates the feature's passes field to true. Use this after you have
    implemented the feature and verified it works correctly.

    Also resets the failure_count to 0.

    Args:
        feature_id: The ID of the feature to mark as passing

    Returns:
        JSON with the updated feature details, or error if not found.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            return json.dumps({"error": f"Feature with ID {feature_id} not found"})

        feature.passes = True
        feature.in_progress = False  # Clear in_progress flag
        feature.failure_count = 0  # Reset failure count on success
        feature.last_error = None  # Clear last error
        session.commit()
        session.refresh(feature)

        return json.dumps(feature.to_dict(), indent=2)
    finally:
        session.close()


@mcp.tool()
def feature_skip(
    feature_id: Annotated[int, Field(description="The ID of the feature to skip", ge=1)]
) -> str:
    """Skip a feature by moving it to the end of the priority queue.

    Use this when a feature cannot be implemented yet due to:
    - Dependencies on other features that aren't implemented yet
    - External blockers (missing assets, unclear requirements)
    - Technical prerequisites that need to be addressed first
    - Repeated tool failures (e.g., Playwright disconnection)

    The feature's priority is set to max_priority + 1, so it will be
    worked on after all other pending features. The failure_count is
    also reset to give the feature a fresh start when it's retried.

    Args:
        feature_id: The ID of the feature to skip

    Returns:
        JSON with skip details: id, name, old_priority, new_priority, message
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            return json.dumps({"error": f"Feature with ID {feature_id} not found"})

        if feature.passes:
            return json.dumps({"error": "Cannot skip a feature that is already passing"})

        old_priority = feature.priority

        # Get max priority and set this feature to max + 1
        max_priority_result = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
        new_priority = (max_priority_result[0] + 1) if max_priority_result else 1

        feature.priority = new_priority
        feature.in_progress = False  # Clear in_progress flag
        feature.failure_count = 0  # Reset failure count for fresh retry
        feature.last_error = None  # Clear last error
        session.commit()
        session.refresh(feature)

        return json.dumps({
            "id": feature.id,
            "name": feature.name,
            "old_priority": old_priority,
            "new_priority": new_priority,
            "message": f"Feature '{feature.name}' moved to end of queue"
        }, indent=2)
    finally:
        session.close()


@mcp.tool()
def feature_record_failure(
    feature_id: Annotated[int, Field(description="The ID of the feature that failed", ge=1)],
    error_message: Annotated[str, Field(description="The error message describing what went wrong")]
) -> str:
    """Record a failure for a feature (increments failure count).

    Use this when a feature fails due to tool errors, timeouts, or other
    issues that prevent successful implementation. This helps track which
    features are problematic and enables automatic skipping after too many
    consecutive failures.

    The failure_count is incremented each time this is called. When the
    count reaches the threshold (5), the feature will be automatically
    skipped on the next feature_get_next call.

    Args:
        feature_id: The ID of the feature that failed
        error_message: Description of what went wrong

    Returns:
        JSON with: feature_id, failure_count, threshold_exceeded, message
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            return json.dumps({"error": f"Feature with ID {feature_id} not found"})

        # Increment failure count
        feature.failure_count = (feature.failure_count or 0) + 1
        feature.last_error = error_message[:500] if error_message else None  # Truncate long errors
        session.commit()
        session.refresh(feature)

        threshold_exceeded = feature.failure_count >= MAX_FEATURE_FAILURES

        return json.dumps({
            "feature_id": feature.id,
            "feature_name": feature.name,
            "failure_count": feature.failure_count,
            "max_failures": MAX_FEATURE_FAILURES,
            "threshold_exceeded": threshold_exceeded,
            "message": f"Recorded failure #{feature.failure_count} for feature '{feature.name}'",
            "warning": "Feature will be auto-skipped on next attempt" if threshold_exceeded else None
        }, indent=2)
    finally:
        session.close()


@mcp.tool()
def feature_create_bulk(
    features: Annotated[list[dict], Field(description="List of features to create, each with category, name, description, and steps")]
) -> str:
    """Create multiple features in a single operation.

    Features are assigned sequential priorities based on their order.
    All features start with passes=false.

    This is typically used by the initializer agent to set up the initial
    feature list from the app specification.

    Args:
        features: List of features to create, each with:
            - category (str): Feature category
            - name (str): Feature name
            - description (str): Detailed description
            - steps (list[str]): Implementation/test steps

    Returns:
        JSON with: created (int) - number of features created
    """
    session = get_session()
    try:
        # Get the starting priority
        max_priority_result = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
        start_priority = (max_priority_result[0] + 1) if max_priority_result else 1

        created_count = 0
        for i, feature_data in enumerate(features):
            # Validate required fields
            if not all(key in feature_data for key in ["category", "name", "description", "steps"]):
                return json.dumps({
                    "error": f"Feature at index {i} missing required fields (category, name, description, steps)"
                })

            db_feature = Feature(
                priority=start_priority + i,
                category=feature_data["category"],
                name=feature_data["name"],
                description=feature_data["description"],
                steps=feature_data["steps"],
                passes=False,
            )
            session.add(db_feature)
            created_count += 1

        session.commit()

        return json.dumps({"created": created_count}, indent=2)
    except Exception as e:
        session.rollback()
        return json.dumps({"error": str(e)})
    finally:
        session.close()


if __name__ == "__main__":
    mcp.run()
