# FR-003 — Unified Execution Client: Pre-Rendered Message Support & `execute()` SDK Method

**Status:** Implemented
**Date:** 2026-03-17
**Priority:** High — blocks SRF Epic 5 (Lobster Discussion Orchestration)
**Source:** CR-001 (submitted by Synthetic Research Forum team), revised to drop `NullExecutionClient`
**Target:** PromptLedger API (`POST /v1/executions/run`) + `promptledger-client` SDK

---

## Problem Statement

Mode 2 (code-managed prompts) currently requires ~20 lines of boilerplate at every LLM call site: build the messages array, call the provider SDK directly, time the call, and manually construct a `SpanPayload` for a separate `POST /v1/spans` call. Every project that adopts Mode 2 reimplements this pattern.

The root cause: the execution API (`POST /v1/executions/run`) only accepts `prompt_name + variables` for Mode 1 (template rendered by PL). Mode 2 projects that construct their own messages have no way to hand off the LLM call to PL — so they call the provider directly, losing automatic span creation and returning no `span_id` to use as a parent for child spans.

After this change, Mode 1 and Mode 2 differ only in **where the prompt is managed**. Execution and span creation are identical:

```
Mode 1:  [prompt in PL DB]  →  PL renders  →  PL calls provider  →  PL logs span  →  result + span_id
Mode 2:  [prompt in code]   →  app renders  →  PL calls provider  →  PL logs span  →  result + span_id
```

PromptLedger is a **hard dependency** for SRF — both services run in the same Railway project on the same private network. The availability tradeoff is accepted: PL being down means SRF is also having a bad day. `NullExecutionClient` is out of scope.

---

## Stories

### Story 3.1 — API: Accept Pre-Rendered `messages` Array

**User Story:**
> As a **developer building a Mode 2 integration**, I want to POST pre-rendered messages to `/v1/executions/run` instead of `prompt_name + variables`, so that I can use dynamic message construction (transcript injection, multi-turn context) while still routing all LLM calls through PromptLedger for automatic span logging and cost tracking.

**Goal:** `POST /v1/executions/run` accepts an optional `messages` array. When present, PL skips template rendering and passes the messages directly to the provider. `prompt_name` remains required for governance and span labeling.

**Schema change:**

New request fields:
```json
{
  "prompt_name": "agent.debate_turn",
  "model": { "provider": "anthropic", "model_name": "claude-sonnet-4-6" },
  "params": { "max_tokens": 600, "temperature": 0.7 },

  "messages": [
    { "role": "system", "content": "You are a research agent..." },
    { "role": "user",   "content": "Full transcript + framing question..." }
  ],

  "span": {
    "trace_id": "srf-2026-w10",
    "parent_span_id": "phase-open-discussion-span-id",
    "agent_id": "paper_1",
    "kind": "llm.generation"
  }
}
```

**Field rules:**

| Field | Mode 1 | Mode 2 (`messages`) |
|---|---|---|
| `prompt_name` | Required | Required (governance + span label) |
| `variables` | Required | Not used — ignored if `messages` present |
| `messages` | Not allowed → 400 | Optional — takes precedence over template rendering |
| `model` | Required | Required |
| `span` | Optional | Optional — if absent, no span is created |

**DB migration required:**

`Execution.rendered_prompt` is currently `NOT NULL`. For Mode 2 with `messages`, there is no rendered prompt string. Changes:
- Make `rendered_prompt` nullable
- Add `messages_json JSONB` column (nullable) to store the messages array for audit/replay
- A row will have either `rendered_prompt` (Mode 1) or `messages_json` (Mode 2) set, never both

**Provider adapter change:**

Both `AnthropicAdapter.generate()` and `OpenAIAdapter.generate()` currently accept `rendered_prompt: str` and wrap it in `[{"role": "user", "content": rendered_prompt}]`. Add an optional `messages` parameter:

```python
async def generate(
    self,
    rendered_prompt: str | None,
    model_name: str,
    params: dict,
    messages: list | None = None,
) -> dict:
    # If messages provided, use directly; otherwise wrap rendered_prompt
    final_messages = messages or [{"role": "user", "content": rendered_prompt}]
```

**Implementation notes:**
- `ExecutionService.execute_sync()` detects `messages` in the request and skips `_render_prompt()`
- Store `messages` in the new `messages_json` column; leave `rendered_prompt` as `None`
- Pass `messages` through to `provider.generate()`
- The prompt's `mode` field is used only for validation (Mode 1 prompts reject `messages`)
- For tracking-mode prompts, `prompt_name` lookup is for governance only — the active version's template is NOT rendered when `messages` is provided

**Acceptance Criteria:**

```gherkin
Feature: Pre-rendered messages input for Mode 2 executions

  Scenario: Execute with messages array routes directly to provider
    Given a registered tracking-mode prompt named "agent.debate_turn"
    And a valid model "anthropic/claude-sonnet-4-6"
    When I POST to /v1/executions/run with:
      """json
      {
        "prompt_name": "agent.debate_turn",
        "model": { "provider": "anthropic", "model_name": "claude-sonnet-4-6" },
        "messages": [
          { "role": "system", "content": "You are a research agent." },
          { "role": "user",   "content": "What is your position on scaling?" }
        ]
      }
      """
    Then the response status should be 200
    And the provider should receive the exact messages array
    And the provider should NOT receive a wrapped single-message array

  Scenario: Messages are persisted for audit
    Given a successful execution using messages input
    When I inspect the execution record in the database
    Then messages_json should contain the submitted messages array
    And rendered_prompt should be NULL

  Scenario: Messages take precedence over variables when both provided
    Given a registered tracking-mode prompt named "agent.debate_turn"
    When I POST with both "messages" and "variables" fields
    Then the provider should receive the messages array
    And the variables should be ignored

  Scenario: Messages rejected for full-mode prompts
    Given a registered full-mode prompt named "doc.summary"
    When I POST to /v1/executions/run with a "messages" array for that prompt
    Then the response status should be 400
    And the error detail should be "messages input not allowed for full-mode prompts — use variables"

  Scenario: Neither messages nor variables provided for tracking prompt
    Given a registered tracking-mode prompt named "agent.debate_turn"
    When I POST to /v1/executions/run with neither "messages" nor "variables"
    Then the response status should be 400
    And the error detail should be "variables or messages required"

  Scenario: Empty messages array is rejected
    Given a registered tracking-mode prompt named "agent.debate_turn"
    When I POST to /v1/executions/run with an empty "messages" array
    Then the response status should be 400
    And the error detail should be "messages array must not be empty"

  Scenario: Unknown prompt_name returns 404
    When I POST to /v1/executions/run with prompt_name "nonexistent.prompt"
    Then the response status should be 404

  Scenario: Mode 1 execution with variables still works unchanged
    Given a registered full-mode prompt named "doc.summary"
    When I POST to /v1/executions/run with "variables" and no "messages"
    Then the response status should be 200
    And the provider receives the rendered template content

  Scenario: AnthropicAdapter passes messages directly to API
    Given messages are provided to the execution service
    When the AnthropicAdapter.generate() is called
    Then it should pass the messages list directly to the Anthropic messages.create() call
    And it should NOT wrap the content in a single user message

  Scenario: OpenAIAdapter passes messages directly to API
    Given messages are provided to the execution service
    When the OpenAIAdapter.generate() is called
    Then it should pass the messages list directly to the OpenAI chat.completions.create() call
    And it should NOT wrap the content in a single user message
```

---

### Story 3.2 — API: Auto-Create Span and Return `span_id`

**User Story:**
> As a **developer building a Mode 2 integration**, I want the execution response to include a `span_id`, so that I can use it as `parent_span_id` for guardrail child spans without making a separate `POST /v1/spans` call.

**Goal:** When the `span` block is present in the request, `POST /v1/executions/run` automatically creates a `Span` record using the execution's telemetry and returns its `span_id`. This eliminates the two-step pattern (execute → separately log span) that Mode 2 projects currently need.

**Response change:**

```json
{
  "execution_id": "uuid",
  "status": "succeeded",
  "mode": "mode2",
  "response_text": "...",
  "span_id": "uuid",
  "telemetry": {
    "prompt_tokens": 4821,
    "response_tokens": 312,
    "latency_ms": 1840,
    "model_name": "claude-sonnet-4-6",
    "provider": "anthropic",
    "total_cost": 0.0058
  }
}
```

`span_id` is `null` if no `span` block was in the request (backwards compatible).

**Span creation rules:**

| `Span` field | Source |
|---|---|
| `trace_id` | `request["span"]["trace_id"]` |
| `parent_span_id` | `request["span"]["parent_span_id"]` (optional) |
| `agent_id` | `request["span"]["agent_id"]` (optional) |
| `kind` | `request["span"]["kind"]` (default: `"llm.generation"`) |
| `prompt_name` | `request["prompt_name"]` |
| `model` | `model.model_name` |
| `prompt_tokens` | from provider response |
| `completion_tokens` | from provider response |
| `duration_ms` | measured during execution |
| `status` | `"ok"` on success, `"error"` on failure |
| `input_data` | `{"messages": messages}` or `{"rendered_prompt": rendered_prompt}` |
| `output_data` | `{"response_text": response_text}` |

The `Span` is linked to the `Execution` via the existing `Execution.span` relationship (the ORM wiring already exists — `span = relationship("Span", back_populates="execution", uselist=False)`). The span is written in the same DB transaction as the execution update.

**Failure behaviour:**
- If span creation fails (e.g., invalid `trace_id` format), the execution result is still returned — span failure must not fail the execution. Log the error and return `span_id: null`.

**Implementation notes:**
- Add `_create_span_for_execution()` private method to `ExecutionService`
- Call it after the provider returns and telemetry is available
- The existing `POST /v1/spans` endpoint remains unchanged — callers who prefer explicit span logging can continue using it

**Acceptance Criteria:**

```gherkin
Feature: Automatic span creation during execution

  Scenario: Span is created and span_id returned when span block provided
    Given a registered tracking-mode prompt and a valid model
    When I POST to /v1/executions/run with a "span" block containing:
      | field          | value              |
      | trace_id       | srf-2026-w10       |
      | parent_span_id | phase-span-abc     |
      | agent_id       | paper_1            |
      | kind           | llm.generation     |
    Then the response status should be 200
    And the response should include a non-null "span_id"
    And a Span record should exist in the database with that span_id

  Scenario: Created span has correct telemetry fields
    Given a successful execution with a "span" block
    When I query the created span from the database
    Then the span should have:
      | field              | value                         |
      | trace_id           | from the span block           |
      | parent_span_id     | from the span block           |
      | agent_id           | from the span block           |
      | prompt_name        | from the request prompt_name  |
      | model              | the resolved model name       |
      | prompt_tokens      | from the provider response    |
      | completion_tokens  | from the provider response    |
      | duration_ms        | measured execution latency    |
      | status             | ok                            |

  Scenario: Span is linked to its execution
    Given a successful execution with a "span" block
    When I load the Execution record and its related Span
    Then execution.span.span_id should match the span_id in the response

  Scenario: Span is queryable via trace summary endpoint
    Given a successful execution with span block containing trace_id "srf-2026-w10"
    When I call GET /v1/traces/srf-2026-w10/summary
    Then the summary should include the new span in its span_count
    And total_prompt_tokens should include the execution's token usage

  Scenario: No span block means span_id is null in response
    Given a registered prompt and valid model
    When I POST to /v1/executions/run without a "span" block
    Then the response status should be 200
    And the response "span_id" field should be null
    And no new Span record should be created

  Scenario: kind defaults to llm.generation when not specified
    Given a POST to /v1/executions/run with a span block that omits "kind"
    When the span is created
    Then the span's kind should be "llm.generation"

  Scenario: Span creation failure does not fail the execution
    Given a span block with a malformed trace_id that causes a DB write error
    When I POST to /v1/executions/run
    Then the response status should be 200
    And the response "span_id" should be null
    And the response should still contain "response_text"
    And the execution record should have status "succeeded"

  Scenario: Mode 1 execution with span block also auto-creates span
    Given a registered full-mode prompt with variables
    And a "span" block in the request
    When I POST to /v1/executions/run
    Then the response should include a non-null "span_id"
    And the span's input_data should contain the rendered_prompt
```

---

### Story 3.3 — SDK: `execute()` Method and `ExecutionResult`

**User Story:**
> As a **developer using `promptledger-client`**, I want a single `client.execute()` method that handles both Mode 1 and Mode 2 calls, so that my call sites are 3–5 lines instead of 20 and I never have to manually construct `SpanPayload` or call `POST /v1/spans` separately.

**Goal:** Add `AsyncPromptLedgerClient.execute()` that calls `POST /v1/executions/run` and returns an `ExecutionResult`. The call site for a Mode 2 debate turn goes from ~20 lines to:

```python
result = await client.execute(
    prompt_name="agent.debate_turn",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": transcript + framing_question},
    ],
    mode="mode2",
    state=state,          # reads trace_id/phase_span_id, writes last_span_id back
    agent_id="paper_1",
    max_tokens=600,
    temperature=0.7,
)
# result.response_text, result.span_id, result.telemetry.total_cost
```

And for Mode 1:

```python
result = await client.execute(
    prompt_name="doc_summarizer",
    variables={"text": document},
    mode="mode1",
    state=state,
    agent_id="summarizer",
)
```

**New SDK files:**

`client/promptledger_client/execution.py`:

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionTelemetry:
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    model_name: str
    provider: str
    total_cost: Optional[float]


@dataclass
class ExecutionResult:
    execution_id: str
    status: str
    response_text: str
    span_id: Optional[str]
    telemetry: ExecutionTelemetry
```

**`execute()` method signature:**

```python
async def execute(
    self,
    prompt_name: str,
    *,
    variables: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    mode: str = "mode2",
    model: Optional[Dict[str, str]] = None,
    state: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: Optional[float] = None,
) -> ExecutionResult:
```

**`state` parameter behaviour:**

If `state` is provided:
- `state["trace_id"]` → `span.trace_id`
- `state.get("phase_span_id")` → `span.parent_span_id`
- After execution: `state["last_span_id"] = result.span_id` (written back in-place)

This eliminates manual span ID threading at every call site in Lobster workflow steps.

**Error mapping:**

| HTTP status | SDK exception |
|---|---|
| 400 | `PromptLedgerError` with message from response detail |
| 401 | `AuthError` (existing) |
| 404 | `NotFoundError` (existing — prompt not found) |
| 5xx | `PromptLedgerError` (existing) |

**`__init__.py` exports:** Add `ExecutionResult`, `ExecutionTelemetry` to `promptledger_client/__init__.py`.

**Acceptance Criteria:**

```gherkin
Feature: AsyncPromptLedgerClient.execute() SDK method

  Scenario: execute() with messages sends correct request body
    Given a mocked POST /v1/executions/run endpoint
    When I call client.execute() with:
      | param        | value               |
      | prompt_name  | agent.debate_turn   |
      | messages     | [{role, content}...] |
      | mode         | mode2               |
      | agent_id     | paper_1             |
      | max_tokens   | 600                 |
    Then the HTTP request body should contain "messages" with the provided array
    And the request body should contain "prompt_name": "agent.debate_turn"
    And the request body should contain "params.max_tokens": 600

  Scenario: execute() with variables sends correct request body for Mode 1
    Given a mocked POST /v1/executions/run endpoint
    When I call client.execute() with:
      | param        | value          |
      | prompt_name  | doc_summarizer |
      | variables    | {"text": "..."}|
      | mode         | mode1          |
    Then the HTTP request body should contain "variables" with the provided dict
    And the request body should NOT contain a "messages" field

  Scenario: execute() returns a populated ExecutionResult
    Given the API returns a successful execution response
    When I call client.execute()
    Then the result should be an ExecutionResult with:
      | field          | value                        |
      | execution_id   | the UUID from the response   |
      | status         | succeeded                    |
      | response_text  | the response text            |
      | span_id        | the span_id from the response|
    And result.telemetry should be an ExecutionTelemetry with prompt_tokens, completion_tokens, latency_ms, total_cost

  Scenario: state dict trace_id and phase_span_id are sent as span block
    Given state = {"trace_id": "srf-2026-w10", "phase_span_id": "phase-abc"}
    When I call client.execute() with state=state
    Then the request body should contain:
      | field                | value        |
      | span.trace_id        | srf-2026-w10 |
      | span.parent_span_id  | phase-abc    |

  Scenario: state dict is updated with last_span_id after execution
    Given state = {"trace_id": "srf-2026-w10"}
    And the API returns span_id "span-xyz-123"
    When I call client.execute() with state=state
    Then state["last_span_id"] should equal "span-xyz-123"

  Scenario: state=None sends no span block
    When I call client.execute() with state=None
    Then the HTTP request body should NOT contain a "span" field
    And result.span_id should be None

  Scenario: 400 response raises PromptLedgerError
    Given the API returns a 400 response with detail "messages array must not be empty"
    When I call client.execute()
    Then a PromptLedgerError should be raised
    And the error message should contain "messages array must not be empty"

  Scenario: 404 response raises NotFoundError
    Given the API returns a 404 response
    When I call client.execute()
    Then a NotFoundError should be raised

  Scenario: 401 response raises AuthError
    Given the API returns a 401 response
    When I call client.execute()
    Then an AuthError should be raised

  Scenario: ExecutionResult and ExecutionTelemetry are importable from package root
    When I run: from promptledger_client import ExecutionResult, ExecutionTelemetry
    Then no ImportError should be raised
```

---

### Story 3.4 — DB Migration

**User Story:**
> As a **PromptLedger operator**, I want the database schema to support storing pre-rendered message arrays without losing the existing rendered prompt audit trail, so that Mode 1 and Mode 2 executions are both fully auditable.

**Goal:** Generate and apply an Alembic migration that makes `rendered_prompt` nullable and adds a `messages_json` JSONB column to the `executions` table.

**Migration changes:**

```sql
ALTER TABLE executions ALTER COLUMN rendered_prompt DROP NOT NULL;
ALTER TABLE executions ADD COLUMN messages_json JSONB;
```

**Invariant (enforced in application layer, not DB constraint):**
- Mode 1 execution: `rendered_prompt` is set, `messages_json` is `NULL`
- Mode 2 execution with `messages`: `rendered_prompt` is `NULL`, `messages_json` is set
- Mode 2 execution with `variables`: `rendered_prompt` is set, `messages_json` is `NULL`

**Steps:**
1. `alembic revision --autogenerate -m "add messages_json to executions, make rendered_prompt nullable"`
2. Review the generated migration — Alembic may not detect the nullability change automatically; verify the `ALTER COLUMN` is present
3. Apply with `alembic upgrade head`
4. Run against a non-empty DB in a test environment before deploying to Railway

**Acceptance Criteria:**

```gherkin
Feature: Database migration for messages_json column

  Scenario: Migration applies cleanly to an empty database
    Given an empty database at the previous schema version
    When I run alembic upgrade head
    Then the executions table should have a nullable rendered_prompt column
    And the executions table should have a messages_json JSONB column
    And alembic_version should reflect the new migration

  Scenario: Migration applies cleanly to a database with existing rows
    Given a database with 10 existing execution rows (all with rendered_prompt set)
    When I run alembic upgrade head
    Then all 10 existing rows should be unchanged
    And rendered_prompt should still be populated for all existing rows
    And messages_json should be NULL for all existing rows

  Scenario: Migration is reversible
    Given the migration has been applied
    When I run alembic downgrade -1
    Then rendered_prompt should be NOT NULL again
    And the messages_json column should no longer exist
    And existing data should be intact

  Scenario: Mode 1 execution writes rendered_prompt and leaves messages_json null
    Given the migration has been applied
    When a Mode 1 execution completes successfully
    Then the execution row should have rendered_prompt set to the rendered template
    And messages_json should be NULL

  Scenario: Mode 2 messages execution writes messages_json and leaves rendered_prompt null
    Given the migration has been applied
    When a Mode 2 execution using messages completes successfully
    Then the execution row should have messages_json set to the submitted messages array
    And rendered_prompt should be NULL
```

---

### Story 3.5 — Integration Guide Update

**User Story:**
> As a **developer integrating PromptLedger into a new project**, I want the integration guide to show the `execute()` pattern for Mode 2, so that I don't have to discover the manual span-logging boilerplate on my own.

**Goal:** Update the integration guide to replace the Mode 2 boilerplate example with `execute()`, update the Mode 1 vs Mode 2 decision table, and add a section on the `state` pattern for stateless workflow engines (e.g., Lobster).

**Sections to update:**

1. **"End-to-End Mode 2 Walkthrough"** — replace the 20-line boilerplate with:

```python
async def prepare_paper_agent(
    paper_text: str,
    framing_question: str,
    client: AsyncPromptLedgerClient,
    state: dict,
) -> str:
    result = await client.execute(
        prompt_name="agent.paper_preparation",
        messages=[
            {"role": "system", "content": PAPER_PREPARATION_SYSTEM_PROMPT},
            {"role": "user",   "content": f"{paper_text}\n\nFraming: {framing_question}"},
        ],
        mode="mode2",
        state=state,
        agent_id="paper-agent-1",
    )
    return result.response_text
```

2. **Mode 1 vs Mode 2 decision table** — update to reflect that the distinction is now purely about prompt management, not execution complexity:

| Choose Mode 1 when | Choose Mode 2 when |
|---|---|
| Non-engineers need to edit prompts without a code deploy | Prompts are code — PR review required for changes |
| You want A/B testing or canary prompt versions | Dynamic message construction needed (transcript injection, multi-turn context) |
| Prompt variables fully describe the call | You want unit-testable prompts with explicit rendering |

3. **New section: "Span ID threading in stateless workflows"** — explain the `state` dict pattern and why `promptledger_client.context` (contextvars) should not be used in multi-step workflow engines like Lobster.

**Acceptance Criteria:**

```gherkin
Feature: Integration guide reflects execute() pattern

  Scenario: Mode 2 walkthrough shows execute() not manual span logging
    Given the updated INTEGRATION_GUIDE.md
    When I read the Mode 2 walkthrough section
    Then it should show client.execute() as the primary call pattern
    And it should NOT show manual SpanPayload construction
    And it should NOT show a separate POST /v1/spans call

  Scenario: Decision table distinguishes modes by prompt management only
    Given the updated INTEGRATION_GUIDE.md
    When I read the Mode 1 vs Mode 2 decision table
    Then the table should NOT mention execution complexity as a differentiator
    And it should describe the distinction as where the prompt template lives

  Scenario: Stateless workflow section explains the state dict pattern
    Given the updated INTEGRATION_GUIDE.md
    When I read the span ID threading section
    Then it should explain why contextvars should not be used in Lobster workflows
    And it should show an example of passing state as a dict across workflow steps
    And it should show state["last_span_id"] being used as parent_span_id for child spans

  Scenario: SRF integration reference updated to prefer execute()
    Given the updated Synthetic_Paper_forum.md Section 10
    When I read section 10.4 (Stateless Span ID Passing)
    Then it should reference client.execute() as the preferred pattern for agent turns
    And the manual log_span() examples should be noted as the lower-level alternative
```

---

### Story 3.6 — Documentation: README, Integration Guide & API Reference

**User Story:**
> As a **developer evaluating or integrating PromptLedger**, I want all documentation to accurately reflect the `execute()` method and the unified execution model, so that I don't waste time following outdated examples or building patterns that FR-003 has made obsolete.

**Goal:** Update every user-facing document that describes the Mode 1/Mode 2 execution model, the Mode 2 boilerplate pattern, or the API surface of `promptledger-client`. After this story, no documentation should describe the old 20-line boilerplate as the recommended Mode 2 integration path.

---

#### README.md

**Changes required:**

1. **Features list** — add `execute()` as a first-class feature and update the Mode 2 description:
   - Add: `Unified execute() Method: Single SDK call for Mode 1 and Mode 2 — automatic span creation, no boilerplate`
   - Update: `Span Ingestion API` bullet to note that `POST /v1/spans` is now the low-level path; `execute()` is the recommended path for most integrations

2. **Architecture diagram** — update the Mode 2 path to show execution flowing through PL rather than directly to the provider:
   ```
   └─► Mode 2: POST /v1/executions/run ─► Provider Adapter ─► Postgres (spans, traces)
               (client constructs messages, PL calls LLM)
   ```
   Remove the current `(client calls LLM directly)` description — it is no longer the recommended path.

3. **Quick Start code example** — if it shows the manual span-logging pattern, replace with `execute()`.

---

#### INTEGRATION_GUIDE.md

**Changes required:**

1. **Section 4 — "When to Choose Mode 2" trade-off table**: Update `Observability setup` row from `~20 lines per call site` to `Automatic via execute()`. Update `Unit testability` row — `tracker=None` pattern is replaced; note that mocking the `execute()` call is straightforward.

2. **Section 5 — "End-to-End Mode 2 Walkthrough"**: Replace the existing manual boilerplate block with the `client.execute()` pattern. Keep the old pattern in a collapsed `<details>` block labelled "Legacy pattern (pre-FR-003) — use execute() instead" so existing integrations aren't broken by the doc change.

3. **Section 7 — "Graceful Degradation Pattern"**: The current section shows `tracker=None` guards around manual `log_span()` calls. Update to show `tracker=None` guards around `execute()` calls instead. Note that `NullExecutionClient` is out of scope.

4. **Section 9 — "Stateless Span-Passing for Workflow Engines"**: This section exists and covers the `state` dict pattern for Lobster. Expand it to show the full `execute()` + `state` integration — reading `phase_span_id` and writing `last_span_id` back. Cross-reference to SRF Section 10.

5. **Section 11 — "API Reference Quick Guide"**: Add `POST /v1/executions/run` with `messages` input to the request examples. Add `span_id` to the response example. Add a note that `POST /v1/spans` remains available for callers that need explicit span control.

6. **Table of Contents**: Section 5 heading should be updated to reflect `execute()` is the primary Mode 2 pattern.

---

#### API Demo Notebook (`examples/api_demo.ipynb`)

The notebook currently has cells demonstrating the manual span-logging boilerplate. Add a new section showing `execute()` end-to-end: register a prompt, call `execute()` with messages, inspect `result.span_id`, then query the trace summary.

---

#### `promptledger-client` SDK `README.md` (`client/README.md`)

If it exists, update the usage example at the top to lead with `execute()` rather than `log_span()`. Add a table showing the three main SDK methods and when to use each:

| Method | When to use |
|---|---|
| `execute()` | All LLM calls — Mode 1 and Mode 2. Automatic span creation. |
| `register_code_prompts()` | At service startup to register/version templates. |
| `log_span()` | Low-level span logging for non-LLM steps (workflow phases, tool calls, guardrail checks that aren't LLM calls). |

---

#### `SRF/requirements/Synthetic_Paper_forum.md` — Section 10

Update Section 10.4 (Stateless Span ID Passing) to note that `client.execute()` is now the preferred pattern for agent turns — it handles span creation automatically and writes `last_span_id` back into the state dict. The manual `log_span()` examples in 10.4 become the reference for non-LLM spans (phase spans, guardrail child spans from non-execute paths).

Update Section 10.3 span hierarchy diagram to show which spans come from `execute()` (agent turns) vs. explicit `log_span()` calls (phase spans, guardrail child spans).

---

**Acceptance Criteria:**

```gherkin
Feature: Documentation reflects unified execute() model

  Scenario: README features list includes execute() as a named capability
    Given the updated README.md
    When I read the Features section
    Then it should include a bullet for the unified execute() method
    And the Mode 2 description should NOT say "client calls LLM directly"

  Scenario: README architecture diagram shows Mode 2 routing through PL
    Given the updated README.md
    When I read the architecture diagram
    Then Mode 2 should show POST /v1/executions/run as the call path
    And it should NOT show the client calling the provider directly

  Scenario: Integration guide trade-off table is updated
    Given the updated INTEGRATION_GUIDE.md Section 4
    When I read the Mode 1 vs Mode 2 trade-off table
    Then the "Observability setup" row should say "Automatic via execute()"
    And it should NOT say "~20 lines per call site"

  Scenario: Integration guide Mode 2 walkthrough leads with execute()
    Given the updated INTEGRATION_GUIDE.md Section 5
    When I read the Mode 2 walkthrough
    Then the primary example should use client.execute()
    And the old manual boilerplate should be in a legacy details block
    And the legacy block should be clearly labelled as pre-FR-003

  Scenario: Integration guide stateless span section shows execute() + state
    Given the updated INTEGRATION_GUIDE.md Section 9
    When I read the stateless span-passing section
    Then it should show execute() reading trace_id and phase_span_id from state
    And it should show state["last_span_id"] being set after the call
    And it should show using last_span_id as parent_span_id for subsequent child spans

  Scenario: API reference shows messages input and span_id response
    Given the updated INTEGRATION_GUIDE.md Section 11
    When I read the POST /v1/executions/run reference entry
    Then the request example should include a "messages" array field
    And the response example should include a "span_id" field

  Scenario: SDK client README leads with execute() usage
    Given the updated client/README.md
    When I read the usage section
    Then execute() should be the first method demonstrated
    And the method comparison table should be present
    And log_span() should be described as the low-level alternative

  Scenario: SRF Section 10 updated to prefer execute() for agent turns
    Given the updated Synthetic_Paper_forum.md Section 10
    When I read Section 10.4
    Then it should show client.execute() as the preferred pattern for agent LLM turns
    And it should note that log_span() is used for phase spans and guardrail child spans
    And the span hierarchy diagram should annotate which spans use execute() vs log_span()

  Scenario: No documentation outside a legacy block describes the 20-line boilerplate as current
    Given all updated documentation files
    When I search for manual SpanPayload construction outside legacy blocks
    Then no current-path examples should show manual span construction for LLM calls
```

**Tasks:**
- [ ] Update `README.md` features list and architecture diagram
- [ ] Update `INTEGRATION_GUIDE.md` Sections 4, 5, 7, 9, 11 and Table of Contents
- [ ] Add `execute()` section to `examples/api_demo.ipynb`
- [ ] Update `client/README.md` usage example and method comparison table
- [ ] Update `requirements/Synthetic_Paper_forum.md` Sections 10.3 and 10.4

---

## Backwards Compatibility

- All existing `POST /v1/executions/run` calls (Mode 1, `prompt_name + variables`) are unchanged
- All existing `POST /v1/spans` calls remain valid — Mode 2 projects that prefer explicit span logging can continue using them
- `register_code_prompts()` and `log_span()` on `AsyncPromptLedgerClient` are unchanged
- `execute()` is a new additive method — no existing SDK code breaks
- `span_id: null` in the response when no `span` block is provided — backwards compatible for callers that don't read this field

---

## Open Questions

1. **Should `POST /v1/executions/submit` (async/Celery path) also accept `messages`?** The Celery task reloads the execution from DB to run it — it would need to use `messages_json` instead of rendering the template. Add ~0.5 day if yes. Recommended: yes, for consistency, but can be a follow-on if it blocks shipping.

2. **`prompt_name` for anonymous Mode 2 executions?** Currently `prompt_name` is required and must exist in the DB. Decision: keep it required — callers using `execute()` will have called `register_code_prompts()` at startup.

---

## Effort Estimate

| Story | Effort |
|---|---|
| 3.1 — API: `messages` input + provider adapter update | M (1.5–2 days) |
| 3.2 — API: auto-create span + return `span_id` | S (0.5 day) |
| 3.3 — SDK: `execute()` + `ExecutionResult` | S (0.5 day) |
| 3.4 — DB migration | S (0.5 day) |
| 3.5 — Integration guide | S (0.5 day) |
| 3.6 — README, API demo notebook, SDK README, SRF Section 10 | S (0.5 day) |
| **Total** | **4–5 days** |
