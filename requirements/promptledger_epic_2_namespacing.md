# PromptLedger Epic 2: Project Namespacing

**Status:** Deferred — not required while each consuming project runs its own dedicated
PromptLedger instance on Railway. Revisit when a shared multi-tenant instance becomes
operationally preferable to per-project deployments.

**Trigger for revisiting:** More than 2-3 projects are using PromptLedger and the overhead
of managing separate Railway deployments (separate Postgres/Redis instances, separate env
vars, separate Railway services) exceeds the implementation cost of this epic.

---

## Problem Statement

All prompts, traces, spans, and analytics in a PromptLedger instance share a single flat
namespace. When multiple applications share one instance:

- **Name collisions** — two projects registering `extraction.paper` overwrite each other.
  Currently `Prompt.name` has a `UNIQUE` constraint with no project scoping.
- **Mixed analytics** — `GET /v1/analytics/prompts` returns totals across all projects.
  There is no way to isolate cost, latency, or execution counts per consuming application.
- **No access isolation** — a single `API_KEY` grants full read/write access to every
  prompt, trace, and span in the instance regardless of which project created it.

**Current workaround:** each project runs its own Railway deployment (separate Postgres,
Redis, API service). This provides isolation at the cost of operational overhead.

---

## Design Decisions (pre-agreed, do not re-litigate)

1. **Project is a first-class entity** — not just a naming prefix. Each project has a UUID,
   a name, and one or more associated API keys.

2. **API keys are database-backed** — the current single `API_KEY` env var becomes a seed
   for the default project's key at startup. New per-project keys are generated via an
   admin endpoint and stored as SHA-256 hashes (never plaintext).

3. **Backwards compatibility** — existing deployments with a single `API_KEY` env var
   continue to work unchanged. The key is seeded as the `"default"` project key on first
   startup after migration.

4. **Auth middleware is rewritten** — replaces the string comparison from Epic 1's Story 1.0
   with a DB lookup by key hash. The resolved `project_id` is attached to request state and
   used by all downstream service queries.

5. **`prompt_name` uniqueness becomes `(project_id, name)`** — the existing
   `UNIQUE(name)` constraint on `prompts` is replaced with `UNIQUE(project_id, name)`.

---

## Prerequisites

- Epic 1 Story 1.0 (auth middleware) must be complete. Epic 2 replaces Story 1.0's simple
  string comparison with a DB-backed key lookup — Story 1.0 establishes the enforcement
  point; Epic 2 upgrades what's behind it.
- A schema design spike (30–60 min) should be completed and signed off before implementation
  begins, confirming the migration sequence doesn't cause downtime on existing Railway
  deployments.

---

## Stories

### Story 2.1 — Projects and API Keys Model

**User Story:**
> As a **PromptLedger operator running a shared instance**, I want each consuming project to have its own database-backed API key, so that I can isolate access per project and revoke individual keys without redeploying the service.

**Goal:** Introduce the `projects` and `api_keys` database tables and seed the existing
`API_KEY` env var as the default project's key.

**Schema (migration 1 of 3):**
```sql
CREATE TABLE projects (
    project_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO projects (name) VALUES ('default');

CREATE TABLE api_keys (
    key_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash    TEXT NOT NULL UNIQUE,   -- SHA-256 of the plaintext key, never stored raw
    project_id  UUID NOT NULL REFERENCES projects(project_id),
    label       TEXT,                   -- human-readable name for the key
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Seeding (at startup, not in migration):**
- Read `settings.api_key`
- Compute `SHA-256(settings.api_key)`
- Upsert into `api_keys` with `project_id = default project`, `label = "legacy env var key"`
- Idempotent — safe to run on every startup

**Auth middleware upgrade:**
- Replace `secrets.compare_digest(header_key, settings.api_key)` with:
  1. Compute `SHA-256(header_key)`
  2. `SELECT project_id FROM api_keys WHERE key_hash = ?`
  3. If not found → 401
  4. Attach `project_id` to `request.state.project_id` for downstream use
- Cache the key→project lookup in memory (TTL: 60s) to avoid a DB hit on every request

**Tests (write first):**
- `API_KEY` env var key authenticates and resolves to the `"default"` project
- Unknown key returns 401
- `request.state.project_id` is set correctly after successful auth
- Auth lookup is cached — second request does not hit the DB

---

### Story 2.2 — Scope Prompts to Project

**User Story:**
> As a **developer on a shared PromptLedger instance**, I want my prompts to live in a separate namespace from other projects, so that two teams can register prompts with the same name without overwriting each other.

**Goal:** Prompt names are unique within a project, not globally. Two projects can register
`extraction.paper` independently.

**Schema (migration 2 of 3):**
```sql
ALTER TABLE prompts ADD COLUMN project_id UUID REFERENCES projects(project_id);
UPDATE prompts SET project_id = (SELECT project_id FROM projects WHERE name = 'default');
ALTER TABLE prompts ALTER COLUMN project_id SET NOT NULL;

-- Drop global unique constraint, replace with scoped one
ALTER TABLE prompts DROP CONSTRAINT prompts_name_key;
ALTER TABLE prompts ADD CONSTRAINT uq_project_prompt_name UNIQUE (project_id, name);
```

**Service changes:**
- All `PromptService` queries add `WHERE prompt_id IN (SELECT ... WHERE project_id = ?)` or
  join on `project_id = request.state.project_id`
- `PUT /v1/prompts/{name}` — scoped to calling project automatically (no body field needed;
  project is resolved from the API key)
- `POST /v1/prompts/register-code` — scoped to calling project automatically
- `GET /v1/prompts` — returns only the calling project's prompts
- `GET /v1/prompts/{name}` — 404 if the prompt belongs to a different project

**Tests (write first):**
- Prompt registered by project A is not visible to project B's API key
- Two projects can register a prompt with the same name — checksums tracked independently
- `GET /v1/prompts` for project A returns only project A's prompts
- `PUT /v1/prompts/{name}` by project B cannot overwrite project A's prompt (404, not 403 —
  the prompt simply doesn't exist in project B's namespace)

---

### Story 2.3 — Scope Spans and Executions to Project

**User Story:**
> As a **PromptLedger operator**, I want traces, spans, and analytics to be isolated per project, so that Project A cannot see Project B's execution data or LLM costs.

**Goal:** Traces, spans, and executions are isolated per project.

**Schema (migration 3 of 3):**
```sql
ALTER TABLE executions ADD COLUMN project_id UUID REFERENCES projects(project_id);
UPDATE executions SET project_id = (SELECT project_id FROM projects WHERE name = 'default');

ALTER TABLE spans ADD COLUMN project_id UUID REFERENCES projects(project_id);
UPDATE spans SET project_id = (SELECT project_id FROM projects WHERE name = 'default');

CREATE INDEX idx_execution_project ON executions(project_id);
CREATE INDEX idx_span_project ON spans(project_id);
```

**Service changes:**
- `POST /v1/spans` — writes `project_id` from `request.state.project_id`
- `GET /v1/traces/{trace_id}` — 404 if the trace belongs to a different project
- `GET /v1/traces/{trace_id}/summary` — scoped to calling project
- `GET /v1/analytics/prompts` — scoped to calling project
- `GET /v1/analytics/agents` — scoped to calling project

**Tests (write first):**
- Span logged by project A is not visible to project B via `GET /v1/traces/{trace_id}`
- `GET /v1/traces/{trace_id}/summary` returns 404 for a trace belonging to another project
- Analytics endpoints return only the calling project's data
- `project_id` appears in the `GET /v1/traces/{trace_id}/summary` response for audit

---

### Story 2.4 — Admin API for Project and Key Management

**User Story:**
> As a **PromptLedger operator**, I want admin endpoints to create named projects and issue scoped API keys, so that I can onboard new consuming teams without manual database changes.

**Goal:** An admin endpoint to create named projects and issue scoped API keys.

**New endpoints:**

`POST /v1/admin/projects` — create a named project and issue its first API key:
```json
// Request
{ "name": "srf", "key_label": "srf-production" }

// Response (key shown exactly once — not stored)
{
  "project_id": "<uuid>",
  "name": "srf",
  "api_key": "pl-<random-64-chars>",
  "key_id": "<uuid>"
}
```

`POST /v1/admin/projects/{project_id}/keys` — issue an additional key for an existing project:
```json
// Request
{ "label": "srf-staging" }

// Response
{ "api_key": "pl-<random-64-chars>", "key_id": "<uuid>" }
```

`DELETE /v1/admin/keys/{key_id}` — revoke a key without deleting the project.

**Security rules:**
- Admin endpoints require the `default` project's API key (the env var key) — only the
  instance owner can create projects and issue keys
- Generated keys use `secrets.token_urlsafe(48)` (64 chars) prefixed with `pl-`
- Only the SHA-256 hash is stored — the plaintext key is returned once and discarded
- Key revocation is immediate; cached auth lookups must be invalidated on DELETE

**Tests (write first):**
- `POST /v1/admin/projects` with a non-default API key returns 403
- `POST /v1/admin/projects` returns a plaintext key and project ID
- Returned key authenticates successfully against a scoped endpoint
- `DELETE /v1/admin/keys/{key_id}` causes subsequent requests with that key to return 401
- Attempting to retrieve the plaintext key after creation is not possible

---

## Implementation Order

```
2.1  Projects + API keys model   (new tables, seeding, auth middleware upgrade)
     ↓
2.2  Prompt scoping              (migration 2, service query changes)
     ↓
2.3  Span + execution scoping    (migration 3, analytics scoping)
     ↓
2.4  Admin API                   (new endpoints, no schema changes)
```

All four stories are sequential — each depends on the previous. No parallelism within this
epic. Estimated effort: 6-8 days.

---

## Backwards Compatibility Contract

1. Existing `API_KEY` env var continues to authenticate — seeded as the default project key
2. All existing prompts, spans, and executions are migrated to the `"default"` project —
   no data loss, no manual intervention required
3. All three schema migrations are non-destructive: columns added and backfilled before
   becoming `NOT NULL`; `UNIQUE(name)` dropped only after `UNIQUE(project_id, name)` is in
   place
4. Projects created via the admin API do not affect the default project in any way

---

## Verification Checklist

```bash
# Story 2.1 — auth upgrade
curl -H "X-API-Key: $LEGACY_KEY" $PL_URL/v1/prompts
# Expect: 200 (legacy key still works, resolves to default project)

# Story 2.2 — prompt scoping
PL_KEY_B=$(curl -X POST $PL_URL/v1/admin/projects -d '{"name":"project-b"}' | jq -r .api_key)
curl -H "X-API-Key: $PL_KEY_B" $PL_URL/v1/prompts
# Expect: empty list (project B sees only its own prompts)

# Story 2.4 — admin API
curl -X DELETE $PL_URL/v1/admin/keys/$KEY_ID -H "X-API-Key: $LEGACY_KEY"
curl -H "X-API-Key: $REVOKED_KEY" $PL_URL/v1/prompts
# Expect: 401
```
