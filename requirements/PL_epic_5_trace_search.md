# Epic 5: Trace Search & Filtering — Query Traces Without Knowing the Trace ID

**Status:** Complete
**Priority:** Now — production debugging is blocked without this

---

## Prerequisites

Epic 1 (span ingestion API) must be complete. Epic 3 (async parity) and Epic 4 (tool call schema) are independent but their data is more useful once search is available.

---

## Context

The only way to retrieve a trace today is `GET /v1/traces/{trace_id}` — you must already know the exact trace ID. In production, the first sign of a problem is usually an error report or an alert, not a trace ID. There is no way to ask "show me all failed traces for agent X in the last hour" or "find traces where prompt Y was used." This makes PromptLedger useful for pre-planned audits but useless for reactive debugging.

---

## What We Gain

| Gap (before) | After this epic |
|---|---|
| Trace retrieval requires knowing the exact trace_id | `GET /v1/traces` supports filtering by agent, status, prompt, and time range |
| Finding a failed trace requires scraping application logs for a trace ID | Developers can search `status=error` directly from PL |
| No way to see all traces for a specific agent or prompt | `agent_id` and `prompt_name` are first-class filter parameters |
| Large result sets return everything with no pagination | Cursor-based pagination caps result size and supports stable iteration |
| No SDK method to search traces | `client.list_traces()` wraps the filter endpoint |

---

## Architecture Decisions

**Cursor-based pagination over offset pagination.** Offset pagination (`LIMIT x OFFSET y`) degrades on large tables and produces inconsistent results when rows are inserted during iteration. Cursor-based pagination using `created_at` + `trace_id` as a compound cursor is stable and performant with the existing index on `spans(trace_id)`.

**Search operates on the `spans` table, not a separate index.** A full-text search engine (Elasticsearch, pg_trgm) is premature. Filtering by `trace_id`, `agent_id`, `status`, `prompt_name`, and time range is achievable with indexed columns and a single aggregating query. Full-text search over span content is deferred to a future epic.

**`GET /v1/traces` returns trace-level summaries, not raw spans.** Each result row is the same shape as `GET /v1/traces/{trace_id}/summary` — aggregate token counts, latency, span count, status. Returning raw spans would produce unbounded payload sizes.

---

## Stories

### Story 5.1 — `GET /v1/traces` List Endpoint with Filters

**As a** developer debugging a production issue,
**I would like** to query `GET /v1/traces` with filter parameters,
**so that** I can find relevant traces without knowing their IDs in advance.

**Files:**
- MODIFY: `src/prompt_ledger/api/v1/endpoints/spans.py` (or new `traces.py` router)
- MODIFY: `src/prompt_ledger/services/span_service.py` (or equivalent)
- MODIFY: `tests/integration/test_traces.py`

**Acceptance Criteria:**

```gherkin
Background:
  Given 5 traces exist: 3 with agent_id "paper_1", 2 with agent_id "paper_2"
  And 2 of the "paper_1" traces have status "error"

Scenario: filter by agent_id returns matching traces only
  When I call GET /v1/traces?agent_id=paper_1
  Then the response should contain exactly 3 traces
  And all returned traces should have agent_id "paper_1"

Scenario: filter by status=error returns only failed traces
  When I call GET /v1/traces?status=error
  Then the response should contain exactly 2 traces
  And all returned traces should have status "error"

Scenario: filter by prompt_name returns traces containing that prompt
  Given 2 traces include a span with prompt_name "agent.debate_turn"
  When I call GET /v1/traces?prompt_name=agent.debate_turn
  Then the response should contain exactly 2 traces

Scenario: time range filter limits results
  Given 3 traces created yesterday and 2 created today
  When I call GET /v1/traces?from=<start_of_today>
  Then the response should contain exactly 2 traces

Scenario: multiple filters are ANDed together
  When I call GET /v1/traces?agent_id=paper_1&status=error
  Then the response should contain only traces that match both conditions

Scenario: no filters returns all traces up to the page limit
  When I call GET /v1/traces with no parameters
  Then the response should contain a "traces" array and a "next_cursor" field

Scenario: invalid status value returns 422
  When I call GET /v1/traces?status=banana
  Then the response status should be 422
```

---

### Story 5.2 — Cursor-Based Pagination

**As a** developer listing traces programmatically,
**I would like** `GET /v1/traces` results to be paginated with a stable cursor,
**so that** I can iterate through large result sets without skipping or duplicating entries.

**Files:**
- MODIFY: `src/prompt_ledger/api/v1/endpoints/spans.py`
- MODIFY: `src/prompt_ledger/services/span_service.py`
- MODIFY: `tests/integration/test_traces.py`

**Acceptance Criteria:**

```gherkin
Background:
  Given 25 traces exist in the database

Scenario: default page size is 20 and next_cursor is returned
  When I call GET /v1/traces
  Then the response should contain 20 traces
  And the response should include a non-null "next_cursor" value

Scenario: using next_cursor returns the remaining page
  Given I have called GET /v1/traces and received a next_cursor
  When I call GET /v1/traces?cursor=<next_cursor>
  Then the response should contain 5 traces
  And the response "next_cursor" should be null

Scenario: page_size parameter overrides the default
  When I call GET /v1/traces?page_size=5
  Then the response should contain 5 traces

Scenario: page_size above maximum is rejected
  When I call GET /v1/traces?page_size=500
  Then the response status should be 422
  And the error should mention the maximum allowed page size

Scenario: invalid cursor value returns 422
  When I call GET /v1/traces?cursor=not-a-valid-cursor
  Then the response status should be 422
```

---

### Story 5.3 — SDK `list_traces()` Method

**As a** developer using `promptledger-client`,
**I would like** a `client.list_traces()` method that wraps the filter endpoint,
**so that** I can search traces from Python code without constructing query strings manually.

**Files:**
- MODIFY: `client/promptledger_client/client.py`
- NEW: `client/promptledger_client/trace_models.py`
- MODIFY: `client/promptledger_client/__init__.py`
- MODIFY: `client/tests/test_client.py`

**Acceptance Criteria:**

```gherkin
Background:
  Given a mocked GET /v1/traces endpoint returning 3 trace summaries

Scenario: list_traces with agent_id filter passes correct query param
  When I call client.list_traces(agent_id="paper_1")
  Then the HTTP request should include query param agent_id=paper_1

Scenario: list_traces returns a list of TraceSummary objects
  When I call client.list_traces()
  Then the result should be a TraceSummaryPage with a "traces" list
  And each item should be a TraceSummary with trace_id, status, span_count, total_cost

Scenario: list_traces passes cursor for pagination
  When I call client.list_traces(cursor="some-cursor-value")
  Then the HTTP request should include query param cursor=some-cursor-value

Scenario: list_traces with no results returns empty list not an error
  Given the API returns an empty traces array
  When I call client.list_traces()
  Then the result traces list should be empty
  And no exception should be raised

Scenario: 401 response raises AuthError
  Given the API returns 401
  When I call client.list_traces()
  Then an AuthError should be raised
```

---

## Implementation Order

```
5.1  GET /v1/traces filter endpoint (core query logic)
     │
     ├── 5.2  Pagination (extends 5.1 — add cursor to same endpoint)
     │
     └── 5.3  SDK list_traces() (depends on 5.1 + 5.2 API being stable)
```

5.2 must complete before 5.3 so the SDK can reflect the paginated response shape.

---

## Verification Checklist

```bash
# After 5.1 — basic filtering
pytest tests/integration/test_traces.py -v -k "list"

# After 5.2 — pagination
pytest tests/integration/test_traces.py -v -k "cursor or pagination"

# After 5.3 — SDK
cd client && pytest tests/test_client.py -v -k "list_traces"

# Full suite
pytest --cov=src/prompt_ledger --cov-fail-under=90
```

---

## Critical Files

- MODIFY: `src/prompt_ledger/api/v1/endpoints/spans.py` (or NEW `traces.py`)
- MODIFY: `src/prompt_ledger/services/span_service.py`
- MODIFY: `client/promptledger_client/client.py`
- NEW: `client/promptledger_client/trace_models.py`
- MODIFY: `client/promptledger_client/__init__.py`
- MODIFY: `tests/integration/test_traces.py`
- MODIFY: `client/tests/test_client.py`
