# SQLite + FastAPI Implementation Plan

## Overview

Replace `feature_list.json` file-based storage with a SQLite database + FastAPI server to reduce token usage and improve scalability.

## Architecture

### Before
```
autonomous_agent_demo.py
    └── agent.py
            └── Reads/writes feature_list.json directly

Claude Agent (in sandbox)
    └── Uses cat/grep/sed to manipulate JSON file
```

### After
```
autonomous_agent_demo.py
    ├── api/server.py (FastAPI in background thread)
    │       ├── api/database.py (SQLite)
    │       ├── api/routes.py (REST endpoints)
    │       └── api/migration.py (JSON → SQLite)
    └── agent.py

Claude Agent (in sandbox)
    └── Uses curl to interact with http://localhost:8765
```

## Files Created

### 1. `api/__init__.py`
Package initialization exporting main classes.

### 2. `api/database.py`
SQLite schema using SQLAlchemy:

```python
class Feature(Base):
    __tablename__ = "features"

    id = Column(Integer, primary_key=True, index=True)
    priority = Column(Integer, nullable=False, default=999, index=True)
    category = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    steps = Column(JSON, nullable=False)  # Array of strings
    passes = Column(Boolean, default=False, index=True)
```

### 3. `api/routes.py`
FastAPI endpoints:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/features` | List features (max 5, supports `random=true`) |
| `GET` | `/features/next` | Get highest-priority pending feature |
| `GET` | `/features/stats` | Get `{passing, total, percentage}` |
| `GET` | `/features/{id}` | Get single feature |
| `POST` | `/features` | Create single feature |
| `POST` | `/features/bulk` | Create features in batch |
| `PATCH` | `/features/{id}` | Update feature (only `passes` field) |
| `POST` | `/features/{id}/skip` | Skip feature (moves to end of priority queue) |
| `DELETE` | `/features/{id}` | Delete feature (use with caution) |
| `GET` | `/health` | Health check |

**Query Parameters for `/features`:**
- `limit` - Max 5 features (hard cap to prevent token waste)
- `offset` - Pagination offset
- `passes` - Filter by pass status (true/false)
- `category` - Filter by category name
- `random` - If true, return random features (for regression testing)

### 4. `api/server.py`
Server lifecycle manager:

```python
class FeatureAPIServer:
    def __init__(self, project_dir, host="127.0.0.1", port=8765)
    def start(self)  # Run migration, start uvicorn in daemon thread
    def stop(self)   # Graceful shutdown
    def is_running(self) -> bool
```

### 5. `api/migration.py`
Auto-migration logic:
1. Check if `feature_list.json` exists
2. Check if database already has data (skip if so)
3. Import JSON into SQLite with proper field mapping
4. Rename JSON to `feature_list.json.backup.<timestamp>`

## Files Modified

### 1. `autonomous_agent_demo.py`
Added server lifecycle around agent loop:

```python
from api.server import FeatureAPIServer

api_server = FeatureAPIServer(project_dir, port=8765)
try:
    api_server.start()
    asyncio.run(run_autonomous_agent(...))
finally:
    api_server.stop()
```

### 2. `progress.py`
Replaced JSON file reads with API calls:
- `count_passing_tests()` -> `GET /features/stats`
- `send_progress_webhook()` -> `GET /features?passes=true` for newly passing

### 3. `agent.py`
Updated first-run detection to check for either JSON file OR SQLite database:
```python
# Old: only checked for JSON
is_first_run = not (project_dir / "feature_list.json").exists()

# New: checks for either storage format
json_file = project_dir / "feature_list.json"
db_file = project_dir / "features.db"
is_first_run = not json_file.exists() and not db_file.exists()
```

### 4. `prompts.py`
Added explicit UTF-8 encoding for cross-platform compatibility:
```python
return prompt_path.read_text(encoding="utf-8")
```

### 5. `prompts/coding_prompt.md`
Updated to use API endpoints (no jq dependency):
```bash
# Get progress stats
curl -s http://localhost:8765/features/stats

# Get next feature to work on
curl -s http://localhost:8765/features/next

# Get random passing features for regression testing
curl -s "http://localhost:8765/features?passes=true&limit=3&random=true"

# Mark feature as passing
curl -X PATCH http://localhost:8765/features/42 \
  -H "Content-Type: application/json" \
  -d '{"passes": true}'
```

Added **API USAGE RULES** section with explicit allowed/forbidden calls to prevent exploratory queries that waste tokens.

### 6. `prompts/initializer_prompt.md`
Replaced file creation with API bulk upload:
```bash
curl -X POST http://localhost:8765/features/bulk \
  -H "Content-Type: application/json" \
  -d '{"features": [...]}'
```

### 7. `requirements.txt`
Added:
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy>=2.0.0
```

## API Response Examples

### GET /features/next
```json
{
  "id": 42,
  "priority": 2,
  "category": "Navigation",
  "name": "Sidebar navigation works",
  "description": "All sidebar links navigate correctly",
  "steps": ["Click Dashboard", "Verify page loads"],
  "passes": false
}
```

### GET /features/stats
```json
{
  "passing": 45,
  "total": 340,
  "percentage": 13.2
}
```

### GET /features?passes=true&limit=3&random=true
```json
{
  "features": [
    {"id": 12, "name": "...", ...},
    {"id": 87, "name": "...", ...},
    {"id": 45, "name": "...", ...}
  ],
  "total": 45,
  "limit": 3,
  "offset": 0
}
```

### POST /features/bulk
Request:
```json
{
  "features": [
    {"category": "functional", "name": "...", "description": "...", "steps": ["..."]}
  ]
}
```
Response: `{"created": 340}`

### POST /features/{id}/skip
Response:
```json
{
  "id": 42,
  "name": "Feature name",
  "old_priority": 5,
  "new_priority": 341,
  "message": "Feature 'Feature name' moved to end of queue"
}
```
Use this when a feature has dependencies on other features that aren't implemented yet.

## Design Decisions

### 1. No jq Dependency
The API returns raw JSON which Claude can parse directly. This avoids requiring `jq` installation on Windows/Mac/Linux.

### 2. Hard Limit Cap (5 features max)
The `/features` endpoint caps `limit` at 5 to prevent agents from making exploratory queries that fetch 20-50 features and waste tokens.

### 3. Random Parameter for Regression Testing
Added `random=true` parameter to return random passing features instead of always the same ones (ordered by priority/ID).

### 4. Strict API Usage Rules in Prompt
Added explicit ALLOWED and FORBIDDEN API calls section to prevent agents from browsing the feature catalog.

### 5. Skip Endpoint for Dependency Handling
Added `POST /features/{id}/skip` to handle cases where a feature cannot be implemented due to dependencies. The endpoint moves the feature to the end of the priority queue (sets priority to max + 1), allowing the agent to work on other features first. This prevents the agent from getting stuck in a loop when it encounters a feature with unmet dependencies.

## Migration Strategy

### For New Projects
1. Server starts with empty database
2. Initializer agent creates features via `POST /features/bulk`
3. Features stored in `features.db`

### For Existing Projects
1. Server starts, detects `feature_list.json`
2. Imports all features into `features.db`
3. Renames JSON to `feature_list.json.backup.<timestamp>`
4. Subsequent sessions use API

## Testing Checklist

- [x] New project: Features created via API
- [x] Existing project: JSON auto-migrated to SQLite
- [x] Limit capped at 5 features max
- [x] Random parameter returns different features each call
- [x] PATCH /features/{id} only allows `passes` field update
- [x] Server starts/stops cleanly with agent lifecycle
- [x] Progress tracking (progress.py) works via API
- [x] Cross-platform compatibility (Windows, Mac, Linux)

## Rollback Plan

If issues occur:
1. Stop the agent
2. Restore from `feature_list.json.backup.<timestamp>`
3. Remove `features.db`
4. Revert code changes
5. Restart agent (will use JSON file)
