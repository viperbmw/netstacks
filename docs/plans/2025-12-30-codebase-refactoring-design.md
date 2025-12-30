# NetStacks Codebase Refactoring Design

**Date:** 2025-12-30
**Status:** Ready for implementation

## Overview

Refactor the NetStacks codebase to improve maintainability by:
1. Fixing the `database_postgres` import bug (breaks scheduled tasks)
2. Splitting monolithic `tasks.py` (1,235 lines) into focused modules
3. Extracting business logic from `app.py` (4,190 lines) into services

## Approach

Incremental refactoring with testing at each step to avoid breaking changes.

---

## Step 1: Fix database_postgres Bug

**Problem:** 5 instances of `import database_postgres as db` reference a non-existent module.

**Files:** `/home/cwdavis/netstacks/tasks.py` (lines 916, 964, 1070, 1123, 1175)

**Fix:** Replace with `import database as db`

**Test:** Verify scheduled tasks can import without error.

---

## Step 2: Split tasks.py into Modules

**Current structure:** Single 1,235-line file with mixed concerns.

**New structure:**
```
netstacks/
├── tasks/
│   ├── __init__.py          # Exports celery_app and all tasks
│   ├── celery_config.py     # Celery app, config, Redis client
│   ├── device_tasks.py      # get_config, set_config, run_commands, validate_config, test_connectivity
│   ├── backup_tasks.py      # backup_device_config, validate_config_from_backup, cleanup_old_backups
│   ├── scheduled_tasks.py   # check_scheduled_operations, execute_scheduled_*
│   ├── template_tasks.py    # render_template_only, sync_netbox_devices
│   └── utils.py             # Parsing helpers (TextFSM, TTP, Jinja2)
├── tasks.py                  # DEPRECATED - backward compat re-exports (remove later)
```

**Migration strategy:**
1. Create `tasks/` directory with new modules
2. Move functions to appropriate modules
3. Update `tasks/__init__.py` to re-export everything
4. Keep old `tasks.py` as thin wrapper for backward compatibility
5. Update workers to import from `tasks` package

---

## Step 3: Extract Services from app.py

**Target reductions:** Move ~2,500 lines out of app.py.

**New services:**
```
netstacks/
├── services/
│   ├── task_history_service.py     # Task tracking (save_task_id, get_task_history)
│   ├── mop_execution_service.py    # MOP step execution (execute_*_step functions)
│   ├── service_stack_service.py    # Stack deployment logic
│   └── netbox_service.py           # NetBox integration
```

**Routes to migrate:**
- Config snapshots → `routes/snapshots.py`
- Task/worker monitoring → `routes/tasks.py`
- Scheduled operations → `routes/scheduling.py`

---

## Testing Strategy

After each step:
1. Run syntax check: `python3 -m py_compile <file>`
2. Restart affected containers: `docker compose restart netstacks workers`
3. Verify application loads: Check docker logs for import errors
4. Test affected functionality via UI or API

---

## File Dependencies

```
tasks/__init__.py
├── celery_config.py (celery_app, Redis client)
├── utils.py (parsing, rendering helpers)
├── device_tasks.py (imports celery_app from celery_config)
├── backup_tasks.py (imports celery_app, utils)
├── template_tasks.py (imports celery_app, utils)
└── scheduled_tasks.py (imports celery_app, database)
```

---

## Backward Compatibility

- `from tasks import celery_app` → Works via `tasks/__init__.py`
- `from tasks import get_config` → Works via re-exports
- Workers import `from tasks import celery_app` → No change needed

---

## Success Criteria

- [ ] No import errors on container restart
- [ ] All Celery tasks discoverable and executable
- [ ] Scheduled tasks run without ImportError
- [ ] UI functionality unchanged
- [ ] app.py reduced to ~1,700 lines
- [ ] tasks.py replaced by tasks/ package
