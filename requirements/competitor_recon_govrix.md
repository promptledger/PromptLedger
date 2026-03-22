# Competitor Recon: Govrix Scout vs PromptLedger

**Date:** 2026-03-22
**Source:** https://govrix.dev/ (live), /docs, /compare, /pricing
**Author:** Claude Code research pass

---

## 1. What Is Govrix?

Govrix Scout is a **transparent Rust reverse-proxy** that sits between AI agents and LLM
provider APIs (OpenAI, Anthropic, Bedrock, etc.). It requires **zero code changes** — the
integrating team sets one environment variable (`OPENAI_BASE_URL=http://localhost:4000/v1`)
and every LLM call flows through the proxy automatically.

Key components:
- `govrix-scout` (port 4000) — the hot-path proxy
- Management API (port 4001) — 17 REST endpoints across agents/costs/events/sessions/policies
- Dashboard (port 3000) — 18-page real-time observability UI
- PostgreSQL 16 + TimescaleDB — event persistence
- Apache 2.0 open source, fully self-hosted, free forever (no tier gating)

Self-reported performance: <1ms p50 added latency (Rust + hyper), <5ms p99.

---

## 2. Feature-by-Feature Comparison

| Capability | PromptLedger | Govrix Scout | Notes |
|---|---|---|---|
| **Integration method** | SDK (`pip install promptledger-client`) + explicit span calls | Zero-code proxy (env var only) | Govrix wins on friction |
| **Prompt versioning** | ✅ SHA-256 content-based versioning, dual-mode (full / tracking) | ❌ No prompt registry | PL exclusive |
| **Prompt execution engine** | ✅ Sync + async (Celery) with provider adapters | ❌ Pass-through only | PL exclusive |
| **LLM call tracing / spans** | ✅ OpenTelemetry-style spans, parent-child tree | ✅ Session + event log, lineage hash | Both; PL is richer tree model |
| **Cost attribution** | ✅ YAML pricing table, total_cost in analytics | ✅ Per-agent, per-model, per-day | Both; similar depth |
| **Agent analytics** | ✅ `GET /v1/analytics/agents` (token/cost by agent) | ✅ Per-agent cost dashboard | Both |
| **Tool call capture** | ✅ `kind=tool` spans, `GET /v1/analytics/tools` | ❌ Not mentioned | PL exclusive (Epic 4) |
| **Project / tenant isolation** | ✅ DB-backed API keys → project_id scoping | ❌ No multi-tenancy | PL exclusive |
| **Multi-tenant admin API** | ✅ `/v1/admin/projects`, key issuance/revocation | ❌ Single-tenant | PL exclusive |
| **PII detection** | ❌ Not implemented | ✅ 25+ patterns, <1ms, in-proxy | **Govrix gap for PL** |
| **Compliance audit trail** | ❌ Not implemented | ✅ SHA-256 Merkle chain per event | **Govrix gap for PL** |
| **Budget / spend enforcement** | ❌ Not implemented | ✅ Per-agent daily/monthly caps + kill switch | **Govrix gap for PL** |
| **Guardrail / policy engine** | ⚠️ Guardrail child spans tracked, no enforcement | ✅ YAML policy rules (block/tag/log) | **Govrix gap for PL** |
| **Kill switch (instant block)** | ❌ Not implemented | ✅ Instant agent disable via API | **Govrix gap for PL** |
| **Streaming (SSE)** | ❌ Not implemented | ✅ SSE pass-through, <5ms overhead | **Govrix gap for PL** |
| **Provider coverage** | ✅ OpenAI, Anthropic (adapter pattern) | ✅ OpenAI, Anthropic, Bedrock, Azure, GCP, Cohere, Mistral, Ollama, LiteLLM | Govrix broader |
| **Agent auto-discovery** | ❌ Requires explicit registration | ✅ Automatic (proxy intercepts all) | **Govrix gap for PL** |
| **Tamper-proof logs** | ❌ Standard Postgres; no hash chain | ✅ Merkle-chained event log | **Govrix gap for PL** |
| **Prometheus metrics** | ❌ Not implemented | ✅ Native Prometheus export | **Govrix gap for PL** |
| **Deployment model** | Docker Compose / Railway (FastAPI + Celery) | Docker / k8s single binary | Both self-hosted |
| **Language** | Python (FastAPI) | Rust (hyper) | PL is slower but more extensible |
| **Dry-run / CI gate** | ✅ `register-code` dry-run, change detection | ❌ Not applicable | PL exclusive |
| **SDK** | ✅ `promptledger-client` (Python async/sync) | REST-only | PL exclusive |
| **A/B testing / evals** | ❌ Roadmap | ❌ Not mentioned | Neither |
| **RBAC / SSO** | ❌ Roadmap | ⚠️ v2 planned (OIDC/SSO) | Both roadmap |
| **Compliance reports** | ❌ Not implemented | ⚠️ v2 planned (SOC 2, EU AI Act, HIPAA) | Govrix has head start |

---

## 3. Where Govrix Clearly Wins

### 3.1 Zero-friction integration
Govrix requires exactly one env var. PromptLedger requires installing an SDK, calling
`register_code_prompts()` at startup, and instrumenting every LLM call with `execute()` or
`log_span()`. This is a significant adoption barrier for teams that want governance without
developer buy-in on every code change.

### 3.2 PII detection — in-proxy, sub-millisecond
Govrix detects SSNs, credit cards, emails, phone numbers, IP addresses in every prompt and
response in the hot path. PromptLedger has no PII capability at all. For healthcare, fintech,
and legal use cases this is a hard requirement.

### 3.3 Tamper-proof audit trail
SHA-256 Merkle chain on every event makes the log forensically sound. PromptLedger stores
spans in standard Postgres with no cryptographic integrity guarantees — a motivated admin
could ALTER a row. This matters for EU AI Act compliance (August 2026 enforcement) and SOC 2.

### 3.4 Budget enforcement + kill switch
Govrix enforces per-agent daily/monthly spend caps at the proxy layer, returning HTTP 403 on
violation. It can also kill a specific agent instantly via API. PromptLedger tracks cost
retroactively via `total_cost` in analytics but has no enforcement or blocking mechanism.

### 3.5 Provider breadth
Govrix proxies any OpenAI-compatible endpoint plus Bedrock, Azure OpenAI, Vertex AI, and
Ollama. PromptLedger's adapter pattern currently covers OpenAI and Anthropic; adding others
requires writing a new adapter class.

### 3.6 Performance
Rust + hyper achieves <1ms p50 added latency. PromptLedger's FastAPI execution path adds
~5–20ms on a warm request (Python GIL, asyncpg round-trip for prompt resolution). For
high-frequency agentic workflows this compounds.

---

## 4. Where PromptLedger Clearly Wins

### 4.1 Prompt registry and versioning
Govrix has no concept of a prompt. It only sees HTTP requests. PromptLedger provides
SHA-256 content-based versioning, deduplication, dual-mode management (database vs code),
and a complete version history per prompt. This is PromptLedger's core value proposition
and has no Govrix equivalent.

### 4.2 Execution engine
PromptLedger can make the LLM call on behalf of the application (`execute()`), render
templates, manage async queue via Celery, and return structured telemetry in one SDK call.
Govrix is pass-through only — it cannot execute prompts.

### 4.3 Tool call structured analytics
Epic 4's `kind=tool` spans with `tool_name`, `success`, `error_rate` aggregated at
`GET /v1/analytics/tools` gives per-tool reliability metrics across runs. Govrix has no
tool-call-level breakdown — costs are attributed to agents, not to the specific tools they
invoke.

### 4.4 Multi-tenancy and project isolation
PromptLedger's project namespacing (Epic 2) lets one deployment serve many consuming
applications with cryptographically separate API keys, project-scoped data, and an admin
API for key lifecycle management. Govrix is single-tenant: one deployment serves one
organization.

### 4.5 SDK and trace model
`promptledger-client` gives developers a typed Python API with `execute()`, `log_span()`,
`log_tool_call()`, `get_trace_summary()`, cursor-paginated `list_traces()`, and
`contextvars` propagation. Govrix offers only a REST API.

### 4.6 Span hierarchy / trace tree
PromptLedger's parent-child span tree (phase → turn → tool/guardrail) models complex
multi-agent ReAct loops natively. Govrix logs a flat event sequence tied to a session —
no parent-child nesting.

---

## 5. Gaps Govrix Exposes in PromptLedger

These are capabilities Govrix ships today that PromptLedger does not have. They represent
potential future epics.

### Gap 1: PII Detection (HIGH impact, HIGH urgency)
**Govrix:** 25+ regex patterns, <1ms, in hot path, flags/masks before or after transmission.
**PromptLedger gap:** Zero PII awareness. Spans store raw `tool_args`, `tool_result`, and
`input_data` / `output_data` JSONB blobs that may contain sensitive data.
**Implication:** PromptLedger is currently unsafe for regulated industries (HIPAA, FINRA,
GDPR) that require PII scrubbing before persistence. Even storing flagged spans in Postgres
may constitute a data handling violation.
**Possible approach:** A `pii_scan` middleware on `POST /v1/spans` that checks
`tool_args`, `tool_result`, `input_data`, `output_data` and either redacts, rejects, or
tags the span before writing.

### Gap 2: Budget Enforcement / Spend Caps (MEDIUM impact)
**Govrix:** Per-agent daily/monthly token and cost caps enforced at proxy with HTTP 403.
**PromptLedger gap:** `total_cost` is computed retroactively in analytics. No mechanism to
pre-empt or block an agent that is over budget.
**Possible approach:** A budget policy table (`project_id`, `agent_id`, `period`,
`cap_usd`) with a pre-execution check in `ExecutionService` and a `POST /v1/spans`
guard using rolling cost from `GET /v1/analytics/agents`.

### Gap 3: Kill Switch (MEDIUM impact)
**Govrix:** `DELETE /v1/agents/{id}/kill` immediately blocks an agent's requests.
**PromptLedger gap:** No mechanism to halt a specific agent mid-flight.
**Possible approach:** An `agent_policy` table with an `enabled` flag checked at span
ingestion and execution time. Flag an agent as disabled via admin API.

### Gap 4: Tamper-Proof Audit Log (MEDIUM impact, HIGH regulatory importance)
**Govrix:** Every event carries a Merkle-chained SHA-256 hash linking it to the prior event.
The chain can be verified independently to prove logs were not altered.
**PromptLedger gap:** Standard Postgres rows. A compromised DB admin or a migration could
silently alter span records.
**Possible approach:** Add a `chain_hash` column to `spans` — `SHA256(span_id ||
previous_chain_hash || trace_id || start_time || tool_name || ...)` — computed server-side
at write time. Expose `GET /v1/traces/{id}/verify` to validate the chain.
**Note:** Full Merkle compliance requires append-only semantics and is architecturally
significant.

### Gap 5: Prometheus Metrics Export (LOW-MEDIUM impact)
**Govrix:** Native `/metrics` endpoint for Prometheus scraping.
**PromptLedger gap:** No metrics endpoint. Health check is the only operational signal.
**Possible approach:** Add `prometheus-client` and expose `GET /metrics` with counters for
`spans_ingested_total`, `executions_total{status}`, `api_key_auth_failures_total`,
`execution_latency_seconds` histogram.

### Gap 6: Streaming / SSE Support (LOW impact for current use case)
**Govrix:** SSE pass-through with <5ms overhead, so streaming responses from the LLM are
observable.
**PromptLedger gap:** `execute()` waits for the full response. No streaming support.
**Note:** Low priority unless SRF workflows need token-by-token streaming (e.g., live
UI display of generation output).

### Gap 7: Agent Auto-Discovery (LOW impact for current use case)
**Govrix:** Agents are discovered automatically from proxy traffic — no registration step.
**PromptLedger gap:** Agents must be explicitly tagged via `agent_id` on spans.
**Note:** PromptLedger's explicit model is actually more precise for analytics (you choose
stable agent names). Auto-discovery is more convenient for existing unmodified codebases.

---

## 6. Competitive Positioning Summary

```
                    Govrix Scout              PromptLedger
                    ─────────────────────     ─────────────────────────
Core strength       Governance / compliance   Prompt management / lineage
Integration         Zero-code (proxy)         SDK + explicit instrumentation
Prompt registry     None                      Full (versioning, templates, modes)
Execution engine    Pass-through only         Native (sync + async Celery)
PII / compliance    ✅ PII, Merkle, budgets    ❌ None
Multi-tenancy       ❌ Single-org              ✅ Project namespacing + admin API
Analytics depth     Agent cost + session      Agent + tool + prompt analytics
Language            Rust (fast, opaque)       Python (slower, extensible)
SDK                 REST-only                 promptledger-client (typed Python)
Open source         Apache 2.0, free forever  [current license TBD]
```

**Positioning conclusion:** Govrix and PromptLedger are largely **complementary**, not
head-to-head competitors. Govrix is the **compliance and governance proxy layer**;
PromptLedger is the **prompt registry and execution lineage layer**. A mature agentic
platform could run both: Govrix to enforce spend caps and detect PII in the hot path,
PromptLedger to version prompts, track tool call reliability, and provide multi-tenant
analytics.

The most concerning gap Govrix exposes is **PII detection** — PromptLedger currently
persists whatever the caller sends in `tool_args`, `tool_result`, and `input_data`, with
no scrubbing. For SRF agents processing academic papers or researcher-authored text this
may be acceptable today, but it becomes a compliance issue the moment agents handle
user-submitted or personally-identifiable content.

---

## 7. Recommended Next Epics (Priority Order)

| Priority | Epic | Rationale |
|---|---|---|
| 1 | PII scan middleware on span ingestion | Compliance blocker for regulated deployments; Govrix has it, we don't |
| 2 | Budget caps + kill switch | Required before SRF agents operate autonomously at scale |
| 3 | Prometheus `/metrics` endpoint | Operational necessity for Railway/k8s monitoring |
| 4 | Merkle audit chain on spans | EU AI Act August 2026; small DB change, big compliance win |
| 5 | Streaming execution (SSE) | Future UX requirement; low urgency now |

---

*Research date: 2026-03-22. Govrix Scout v1 is live; v2 features (RBAC, compliance reports,
mTLS) are announced but not yet shipped. Re-check quarterly.*
