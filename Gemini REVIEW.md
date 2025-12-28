# NetStacks Code and Architecture Review

## 1. Executive Summary

**Project Status:** Functional prototype / Transitional state
**Architecture:** Hybrid (Monolithic core with Microservices scaffolding)
**Assessment:** The project contains a rich set of features for network automation (MOP engine, visual builders, multi-vendor support). However, it currently suffers from significant architectural debt, primarily due to an overloaded monolithic application file (`app.py`), circular dependencies, and a mix of architectural patterns (monolith vs. microservices) that are not fully reconciled.

## 2. Architecture Analysis

### Current State: The "Hybrid Monolith"
Although the directory structure and `docker-compose.yml` suggest a microservices architecture (with services like `auth`, `devices`, `config` running in separate containers), the application logic behaves largely as a monolith.

*   **The Facade:** The `netstacks` container (Flask) acts as the primary entry point and handles almost all business logic.
*   **The Phantom Microservices:** Services like `auth`, `devices`, and `config` are defined in Docker but their Traefik labels are commented out. The main Flask app (`netstacks`) typically calls its own internal modules rather than making HTTP requests to these services.
*   **Data Layer:** PostgreSQL is the backing store, accessed via SQLAlchemy. The database models are shared code, which creates tight coupling if services attempt to access the DB directly (as seen in `tasks.py`).

### Architectural Issues
1.  **Circular Dependencies:** `app.py` imports `mop_engine`, while `mop_engine` imports functions back from `app.py` (e.g., `execute_deploy_stack_step`). This indicates high coupling and makes testing or refactoring difficult.
2.  **Overloaded Entry Point:** `app.py` handles routing, business logic, authentication, database calls, and Celery task dispatching. It violates the Single Responsibility Principle.
3.  **Worker-Database Coupling:** The Celery workers (`tasks.py`) import database logic directly. In a scalable distributed system, workers should ideally be stateless or interact with a service API, rather than sharing a database connection and ORM models with the web frontend.

## 3. Code Quality Review

### `netstacks/app.py`
*   **Size & Complexity:** Excessive length (~2000 lines). Acts as a "God Object."
*   **Routing:** While some routes are migrated to blueprints (`routes/`), many remain in `app.py`, creating inconsistent routing logic.
*   **Global State:** Heavy reliance on global imports and potentially global state (e.g., `device_cache` dictionary defined at module level).

### `netstacks/mop_engine.py`
*   **Design:** Clean class-based design (`MOPEngine`). The YAML-based definition philosophy is sound and user-friendly.
*   **Implementation:** The dependency on `app.py` for executing steps (`from app import ...`) hinders its portability. It should be a standalone library that accepts execution callbacks or uses a service interface.

### `netstacks/tasks.py` (Worker)
*   **Capabilities:** Strong network interaction logic using Netmiko, TextFSM, and Genie.
*   **Structure:** Mixes task definitions with helper logic and scheduling code (`Celery Beat` tasks).
*   **Data Access:** Direct imports of `database_postgres` creates a shared dependency that complicates splitting the worker into a separate deployment unit if the DB schema changes.

### `netstacks/services/celery_device_service.py`
*   **Pattern:** Good use of the Service pattern to wrap Celery task dispatching. This provides a clean interface for the rest of the application to trigger async jobs.

## 4. Security Review

### Authentication
*   **Implementation:** Supports Local, LDAP, and OIDC. Logic is partially modular (`auth_ldap.py`, `auth_oidc.py`) but the core switching logic resides in `app.py`'s `authenticate_user`.
*   **Storage:** Credentials appear to use encryption (`credential_encryption.py`), which is a best practice.

### MOP Engine Sandboxing
*   **Mechanism:** Uses regex (`DANGEROUS_PATTERNS`) and `exec` with restricted `globals` to sandbox Python code.
*   **Risk:** Regex-based filtering is rarely sufficient to stop determined attackers in Python (e.g., obfuscated imports).
*   **Recommendation:** For a production system allowing user-defined code, consider stronger isolation like running execution steps in ephemeral Docker containers or using a dedicated sandboxing library (e.g., `RestrictedPython` or WebAssembly/WASM).

## 5. Recommendations

### Immediate Priority (Refactoring)
1.  **Break up `app.py`**:
    *   Move all remaining routes to blueprints in `routes/`.
    *   Move core business logic (e.g., `authenticate_user`, `cleanup_orphaned_backups`) to dedicated service modules in `services/`.
2.  **Decouple MOP Engine**:
    *   Refactor `MOPEngine` to accept `execution_handlers` as a dependency injection or configuration, removing the `import from app` circular dependency.
3.  **Standardize Configuration**:
    *   Consolidate environment variable loading and defaults into `config.py`.

### Medium Term (Architecture)
1.  **Commit to Microservices or Monolith**:
    *   *If Monolith:* Remove the unused microservice containers from `docker-compose`. Organize code by domains (Auth, Devices, Config) within the monolith.
    *   *If Microservices:* Fully separate the services. Ensure `netstacks` UI talks to `auth`/`device` services via HTTP API, not internal function calls.
2.  **Worker Isolation**:
    *   Refactor workers to fetch necessary data from the API or job parameters rather than connecting to the primary SQL database directly, or strictly define the "Shared Database" pattern boundaries.

### Long Term
1.  **Enhanced Sandboxing**: Replace `exec()` based sandboxing with container-based execution for custom Python steps.
2.  **API Documentation**: Complete the migration to FastAPI (hinted at in `Netstacker` references) or use Flask-RESTX/Marshmallow for strict API schemas and Swagger documentation.

## 6. Conclusion
NetStacks is a promising tool with a strong feature set for network engineers. The visual MOP builder and multi-vendor support are significant value propositions. To become a production-grade enterprise platform, the project must prioritize **decoupling the monolithic `app.py`** and **resolving circular dependencies**. Stability and maintainability will improve drastically with these refactors.
