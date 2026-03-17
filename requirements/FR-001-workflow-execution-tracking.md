# Feature Request: Workflow Execution Tracking

**FR-001** | **Priority:** High | **Status:** Proposed
**Author:** Development Team | **Date:** January 19, 2026

---

## Executive Summary

Enable PromptLedger to track and correlate prompt executions across multi-step agentic workflows without implementing workflow orchestration. Users bring their own workflow engines; PromptLedger provides passive observability and correlation capabilities.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Requirements](#requirements)
3. [Why This Matters](#why-this-matters)
4. [Proposed Alternatives](#proposed-alternatives)
5. [Pairwise Analysis](#pairwise-analysis)
6. [Recommendation](#recommendation)
7. [Appendix](#appendix)

---

## Problem Statement

### Current State

PromptLedger tracks individual prompt executions with basic correlation via `correlation_id`. However, modern LLM applications are increasingly built as **agentic workflows**—multi-step pipelines where outputs from one prompt feed into another.

**Example: HR Policy Assistant Workflow**
```
User Question
    → RAG Retrieval
    → Response Generation
    → Grounding Guardrail
    → Structure Guardrail
    → Final Response
```

### The Gap

Users cannot currently answer critical questions:

| Question | Current Capability |
|----------|-------------------|
| "Show me all steps in workflow run X" | ❌ No grouping mechanism |
| "What was the total token cost for this request?" | ❌ No aggregation |
| "Which step caused the failure?" | ❌ No step identification |
| "What was the chain of reasoning?" | ❌ No lineage tracking |
| "How long did the full workflow take?" | ❌ No end-to-end timing |

### Constraints

1. **PromptLedger must NOT become a workflow engine** — users control orchestration
2. **Must be agnostic** to workflow framework choice (LangChain, LlamaIndex, custom, etc.)
3. **Minimal integration burden** — should not require users to contort their code
4. **Support diverse patterns** — linear chains, parallel fan-out, ReAct loops, nested agents

---

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Group related executions by a user-provided identifier | Must Have |
| FR-2 | Track parent-child relationships between executions | Must Have |
| FR-3 | Support human-readable step labels | Should Have |
| FR-4 | Aggregate telemetry (tokens, latency) across grouped executions | Must Have |
| FR-5 | Query executions by group identifier | Must Have |
| FR-6 | Retrieve execution chain/tree for a given execution | Should Have |
| FR-7 | Support parallel execution patterns (fan-out/fan-in) | Must Have |
| FR-8 | Support iterative patterns (ReAct loops, retries) | Should Have |
| FR-9 | Record external LLM calls not executed through PromptLedger | Should Have |
| FR-10 | Distinguish execution types (generation, guardrail, tool, retrieval) | Could Have |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Integration requires ≤2 additional fields per execution | Usability |
| NFR-2 | No breaking changes to existing API | Compatibility |
| NFR-3 | Query performance <100ms for workflow retrieval | Performance |
| NFR-4 | Familiar mental model for users of observability tools | Usability |

---

## Why This Matters

### 1. Industry Trend: Agentic Architectures

The LLM industry is rapidly shifting from single-prompt applications to agentic workflows:

- **OpenAI Agents SDK** — Multi-step agent orchestration
- **LangChain/LangGraph** — DAG-based prompt chains
- **AutoGPT, CrewAI** — Autonomous multi-agent systems
- **Enterprise RAG** — Retrieval → Generation → Validation pipelines

PromptLedger must evolve to track these patterns or become irrelevant for modern use cases.

### 2. Debugging and Observability

When a workflow fails or produces poor results, users need to:
- Identify which step failed
- Understand what inputs led to the failure
- Compare successful vs failed workflow runs
- Trace the chain of reasoning

Without execution correlation, debugging multi-step workflows requires manual log correlation across multiple systems.

### 3. Cost Attribution

Token costs accumulate across workflow steps. Organizations need to:
- Attribute costs to specific workflows/features
- Identify expensive steps for optimization
- Compare cost efficiency across workflow versions

### 4. Compliance and Auditability

Regulated industries require complete audit trails:
- "Show me every LLM call made to answer this customer's question"
- "Prove that guardrails were executed before the response was sent"
- "Reconstruct the decision chain for this output"

### 5. Competitive Positioning

Tools like LangSmith, Arize Phoenix, and Weights & Biases Prompts already offer workflow tracing. PromptLedger must provide comparable capabilities to remain competitive.

---

## Proposed Alternatives

### Option A: Minimal Extension (workflow_run_id Only)

**Description:** Add a single `workflow_run_id` field to the Execution model. Users provide this ID to group related executions. No structural changes to relationships.

**Schema Changes:**
```python
class Execution(Base):
    # Existing fields...

    # New field
    workflow_run_id = Column(String(100), index=True)
```

**API Changes:**
```python
# Execute with workflow grouping
POST /v1/prompts/{name}/execute
{
    "workflow_run_id": "wf-abc123",
    "variables": {...}
}

# Query by workflow
GET /v1/executions?workflow_run_id=wf-abc123
```

**Pros:**
- Minimal implementation effort (1 field, 1 index)
- No breaking changes
- Simple mental model
- Covers 70% of use cases (basic grouping)

**Cons:**
- No parent-child relationships (can't trace chains)
- No step labeling (steps are anonymous)
- No support for parallel/nested patterns
- Limited aggregation capabilities
- Users must build lineage tracking themselves

**Effort:** ~2 days

---

### Option B: Extended Correlation Model

**Description:** Add multiple correlation fields to capture grouping, lineage, and step metadata. Keep all fields optional for progressive adoption.

**Schema Changes:**
```python
class Execution(Base):
    # Existing fields...

    # New correlation fields
    workflow_run_id = Column(String(100), index=True)
    parent_execution_id = Column(UUID, ForeignKey("executions.execution_id"))
    step_name = Column(String(100))
    step_order = Column(Integer)
    step_type = Column(String(50))  # "generation", "guardrail", "retrieval", "tool"
    step_metadata = Column(JSONB)

    # Self-referential relationship
    parent_execution = relationship("Execution", remote_side=[execution_id])
    child_executions = relationship("Execution", back_populates="parent_execution")
```

**API Changes:**
```python
# Execute with full correlation
POST /v1/prompts/{name}/execute
{
    "workflow_run_id": "wf-abc123",
    "parent_execution_id": "exec-previous",
    "step_name": "grounding_check",
    "step_type": "guardrail",
    "step_metadata": {"threshold": 0.8},
    "variables": {...}
}

# Query by workflow with aggregation
GET /v1/executions?workflow_run_id=wf-abc123

# Get execution tree
GET /v1/executions/{id}/tree

# Aggregate telemetry
GET /v1/workflows/{workflow_run_id}/summary
```

**Pros:**
- Supports all workflow patterns (chains, trees, parallel)
- Step labeling for debugging
- Full lineage tracking
- Rich aggregation capabilities
- All fields optional — progressive adoption

**Cons:**
- More complex implementation
- More fields for users to understand
- Self-referential FK adds query complexity
- Custom terminology (not industry-standard)

**Effort:** ~5 days

---

### Option C: OpenTelemetry-Aligned Trace/Span Model

**Description:** Adopt industry-standard observability terminology (traces and spans). Add a dedicated Span model that can represent both prompt executions and external operations (tool calls, retrievals). Link Spans to Executions where applicable.

**Schema Changes:**
```python
class Span(Base):
    """Observability span for workflow tracking."""
    __tablename__ = "spans"

    span_id = Column(UUID, primary_key=True, default=uuid4)
    trace_id = Column(String(100), nullable=False, index=True)
    parent_span_id = Column(UUID, ForeignKey("spans.span_id"))

    # Identity
    name = Column(String(100), nullable=False)
    kind = Column(String(50), nullable=False)  # "llm", "tool", "retrieval", "guardrail", "agent"

    # Timing
    start_time = Column(DateTime, nullable=False, server_default=func.now())
    end_time = Column(DateTime)
    duration_ms = Column(Integer)

    # Status
    status = Column(String(20), default="ok")  # "ok", "error"
    error_message = Column(Text)

    # Content (flexible)
    input_data = Column(JSONB)
    output_data = Column(JSONB)
    attributes = Column(JSONB)  # Arbitrary metadata

    # Link to execution (if this span is a prompt execution)
    execution_id = Column(UUID, ForeignKey("executions.execution_id"))

    # Telemetry (for LLM spans)
    model = Column(String(100))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)

class Execution(Base):
    # Existing fields unchanged...

    # New: optional link to span
    span = relationship("Span", back_populates="execution", uselist=False)
```

**API Changes:**
```python
# Option 1: Execute prompt with trace context
POST /v1/prompts/{name}/execute
{
    "trace_id": "trace-abc123",
    "parent_span_id": "span-previous",
    "span_name": "generate_response",
    "variables": {...}
}

# Option 2: Record external operation (passive logging)
POST /v1/traces/{trace_id}/spans
{
    "parent_span_id": "span-abc",
    "name": "openai_direct_call",
    "kind": "llm",
    "input_data": {"messages": [...]},
    "output_data": {"response": "..."},
    "model": "gpt-4o",
    "prompt_tokens": 150,
    "completion_tokens": 89,
    "duration_ms": 450
}

# Query trace
GET /v1/traces/{trace_id}
GET /v1/traces/{trace_id}/spans
GET /v1/traces/{trace_id}/tree
GET /v1/traces/{trace_id}/summary
```

**Pros:**
- Industry-standard terminology (familiar to users of DataDog, Jaeger, LangSmith)
- Supports ALL patterns (chains, trees, parallel, nested)
- Can track non-prompt operations (tools, retrievals)
- Passive logging for external LLM calls
- Clean separation: Spans for observability, Executions for prompt-specific data
- Future-proof: can integrate with OpenTelemetry ecosystem

**Cons:**
- Most complex implementation
- New Span table and relationships
- Two concepts to understand (Span vs Execution)
- Migration path needed for existing users
- Potential confusion: when to use Span vs Execution?

**Effort:** ~10 days

---

## Pairwise Analysis

### Option A vs Option B: Minimal vs Extended

| Dimension | Option A (Minimal) | Option B (Extended) | Verdict |
|-----------|-------------------|---------------------|---------|
| **Implementation Effort** | ~2 days | ~5 days | A wins |
| **User Learning Curve** | 1 field | 5+ fields | A wins |
| **Chain/Tree Tracking** | ❌ Not supported | ✅ Full support | B wins |
| **Step Labeling** | ❌ Not supported | ✅ Supported | B wins |
| **Parallel Patterns** | ⚠️ Grouping only | ✅ Parent-child trees | B wins |
| **External Call Logging** | ❌ Not supported | ❌ Not supported | Tie |
| **Progressive Adoption** | ✅ Already minimal | ✅ All fields optional | Tie |
| **Covers Use Cases** | ~70% | ~90% | B wins |

**Verdict:** Option B is superior for real-world agentic workflows. The additional complexity is justified by significantly better debugging and tracing capabilities. **Option A is too limited** for production agentic systems.

---

### Option B vs Option C: Extended vs Trace/Span

| Dimension | Option B (Extended) | Option C (Trace/Span) | Verdict |
|-----------|--------------------|-----------------------|---------|
| **Implementation Effort** | ~5 days | ~10 days | B wins |
| **Industry Alignment** | Custom terminology | OpenTelemetry standard | C wins |
| **User Familiarity** | New concepts to learn | Familiar to observability users | C wins |
| **External Call Logging** | ❌ Not supported | ✅ Full support | C wins |
| **Non-Prompt Operations** | ❌ Only prompt executions | ✅ Tools, retrievals, etc. | C wins |
| **Schema Complexity** | Moderate (5 fields) | Higher (new table) | B wins |
| **Integration Ecosystem** | Standalone | Can export to OTel tools | C wins |
| **Mental Model Clarity** | One entity (Execution) | Two entities (Span + Execution) | B wins |
| **Future Extensibility** | Limited | High | C wins |

**Verdict:** Option C is architecturally superior and future-proof. The trace/span model is battle-tested in observability and will be immediately familiar to users of LangSmith, Arize, or any APM tool. However, **Option B is a pragmatic middle ground** if implementation resources are constrained.

---

### Option A vs Option C: Minimal vs Trace/Span

| Dimension | Option A (Minimal) | Option C (Trace/Span) | Verdict |
|-----------|-------------------|-----------------------|---------|
| **Implementation Effort** | ~2 days | ~10 days | A wins |
| **Capability Coverage** | ~70% | ~99% | C wins |
| **Production Readiness** | Limited | Full | C wins |
| **Technical Debt** | Creates debt (will need extension) | Minimal debt | C wins |
| **Time to Value** | Immediate | Longer | A wins |

**Verdict:** Option A could serve as a quick interim solution, but **will create technical debt** requiring rework. Option C is the correct long-term investment.

---

## Recommendation

### Primary Recommendation: Option C (Trace/Span Model)

**Rationale:**

1. **Industry Alignment**: The trace/span model is the industry standard for distributed system observability. Users familiar with OpenTelemetry, DataDog, Jaeger, or LangSmith will find it immediately intuitive.

2. **Complete Coverage**: Supports all agentic patterns—linear chains, parallel fan-out, nested agents, ReAct loops, and retries—without workarounds.

3. **External Call Logging**: The ability to passively record LLM calls made outside PromptLedger (direct OpenAI calls, other providers) is critical for complete workflow visibility. Options A and B cannot support this.

4. **Future-Proof**: The trace/span model positions PromptLedger for future OpenTelemetry integration, enabling export to existing observability infrastructure.

5. **Clean Separation of Concerns**: Spans handle observability/correlation; Executions handle prompt-specific versioning and management. This separation is architecturally sound.

### Implementation Strategy

**Phase 1 (Week 1):** Core Span model and basic API
- Create Span table with trace_id, parent_span_id, name, kind
- Add trace context fields to execution endpoints
- Implement `GET /v1/traces/{trace_id}` query

**Phase 2 (Week 2):** Passive logging and aggregation
- Implement `POST /v1/traces/{trace_id}/spans` for external call logging
- Add aggregation endpoint `GET /v1/traces/{trace_id}/summary`
- Build tree retrieval `GET /v1/traces/{trace_id}/tree`

**Phase 3 (Future):** Advanced features
- OpenTelemetry export integration
- Trace comparison tools
- Anomaly detection across traces

### Fallback: Option B (If Resources Constrained)

If the 10-day implementation timeline for Option C is not feasible, **Option B provides 90% of the value at 50% of the cost**. However, note that:

1. External call logging will remain unsupported
2. Custom terminology may create friction for users familiar with observability tools
3. Future migration to trace/span model may require breaking changes

### Not Recommended: Option A

Option A is **not recommended** for production implementation. While simple, it creates technical debt and will require significant rework as user needs evolve. The ~70% use case coverage is insufficient for production agentic workflows.

---

## Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| **Trace** | A collection of spans representing a single workflow execution from start to finish |
| **Span** | A single operation within a trace (prompt execution, tool call, retrieval, etc.) |
| **trace_id** | Unique identifier grouping all spans in one workflow run |
| **span_id** | Unique identifier for a single span |
| **parent_span_id** | Reference to the span that triggered this span (enables tree structure) |

### B. Competitive Landscape

| Tool | Workflow Tracking Model | Notes |
|------|------------------------|-------|
| **LangSmith** | Trace/Run hierarchy | Industry leader, OpenTelemetry-aligned |
| **Arize Phoenix** | Trace/Span | OpenTelemetry native |
| **Weights & Biases** | Trace/Span | Recent addition |
| **Helicone** | Session/Request | Simpler model |
| **PromptLayer** | Request grouping | Basic correlation |

### C. User Story Examples

**Story 1: Debug Failing Workflow**
> As a developer, I want to see all steps executed in a failed workflow run so that I can identify which step caused the failure and with what inputs.

**Story 2: Cost Attribution**
> As a product manager, I want to see total token costs grouped by workflow type so that I can prioritize optimization efforts.

**Story 3: Compliance Audit**
> As a compliance officer, I want to retrieve the complete execution chain for any customer-facing response so that I can demonstrate guardrails were applied.

**Story 4: External Call Tracking**
> As a developer using OpenAI directly in some steps, I want to log those calls to PromptLedger so that I have complete workflow visibility in one place.

### D. Migration Path

For existing users:
1. All new fields are optional — existing integrations continue working
2. `correlation_id` remains supported for backward compatibility
3. `trace_id` is recommended for new integrations
4. Documentation will provide migration guide from correlation_id to trace_id

---

## Approval

| Role | Name | Date | Decision |
|------|------|------|----------|
| Product Owner | | | |
| Tech Lead | | | |
| Architecture | | | |

---

*Document Version: 1.0*
*Last Updated: January 19, 2026*
