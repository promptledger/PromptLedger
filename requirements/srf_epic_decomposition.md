# Synthetic Research Forum — Technical Specification

## Overview

A structured multi-agent discussion system that convenes moderated conversations between AI agents grounded in specific research papers, synthesizing emerging AI research into dynamic dialogues. Each weekly discussion takes up to 3 papers from the newsletter, assigns each to an agent that argues from that paper's perspective, and runs a bounded, moderated conversation orchestrated via OpenClaw and Lobster workflows. A human editor reviews the final transcript before publication.

**Version:** 1.6
**Date:** 2026-03-07
**Orchestration:** OpenClaw Gateway + Lobster Workflow Engine
**Deployment:** Railway (Serverless sleeping, manual trigger)
**Execution Model:** Programmatic/headless — direct agent-to-agent exchange, Moderator as referee
**Output Format:** Structured JSON (canonical) + Markdown (rendered)
**Editorial Model:** Post-discussion review only
**Estimated Monthly Cost:** ~$7-8 Railway (OpenClaw + PromptLedger + PostgreSQL + Redis, all Serverless sleeping) + ~$16-18 Anthropic API

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Agent Model](#agent-model)
3. [Discussion Protocol](#discussion-protocol)
4. [Output Schema](#output-schema)
5. [Epic Breakdown](#epic-breakdown)
6. [User Stories with Gherkin](#user-stories-with-gherkin)
7. [Development Roadmap](#development-roadmap)
8. [Success Criteria](#success-criteria)

---

## System Architecture

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        EDITORIAL LAYER                            │
│  ┌──────────────────────┐       ┌──────────────────────────┐     │
│  │ Human Editor          │       │ Published Output          │     │
│  │ (Review & Curate)     │       │ (Newsletter Companion)    │     │
│  └──────────┬────────────┘       └──────────▲───────────────┘     │
└─────────────┼────────────────────────────────┼────────────────────┘
              │ Review/Approve                 │ Publish
              │                                │
┌─────────────▼────────────────────────────────┼────────────────────┐
│                RAILWAY (Serverless / Sleeping)                      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │           Lobster Workflow Engine                          │     │
│  │  ┌────────────────────────────────────────────────┐      │     │
│  │  │ Phases:                                         │      │     │
│  │  │  1. workspace_generation (Paper Agent setup)    │      │     │
│  │  │  2. opening (Moderator frames topic)            │      │     │
│  │  │  3. position_statements (each agent presents)   │      │     │
│  │  │  4. open_discussion (direct agent exchange)     │      │     │
│  │  │  5. closing_statements (final positions)        │      │     │
│  │  │  6. synthesis (Synthesis Agent summarizes)       │      │     │
│  │  │  7. output_generation (JSON + Markdown)         │      │     │
│  │  └────────────────────────────────────────────────┘      │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │              OpenClaw Gateway                             │     │
│  │  ┌────────────────────────────────────────────────┐      │     │
│  │  │ Agents (per discussion):                        │      │     │
│  │  │  - moderator   (Claude Opus, facilitator)       │      │     │
│  │  │  - paper_1..3  (Claude Sonnet, per-paper)       │      │     │
│  │  │  - guardrail   (Claude Sonnet, real-time checks) │      │     │
│  │  │  - synthesizer (Claude Opus, post-discussion)   │      │     │
│  │  └────────────────────────────────────────────────┘      │     │
│  │                                                           │     │
│  │  Per-Agent Workspaces (on /data volume):                  │     │
│  │    /data/workspace/forum/moderator/                       │     │
│  │      ├── SOUL.md      (facilitator persona)               │     │
│  │      ├── AGENTS.md    (discussion protocol rules)         │     │
│  │      └── TOOLS.md     (transcript access)                 │     │
│  │    /data/workspace/forum/paper-N/                         │     │
│  │      ├── SOUL.md      (paper-grounded persona)            │     │
│  │      ├── AGENTS.md    (argumentation rules)               │     │
│  │      ├── context/     (paper PDF, abstract, claims)       │     │
│  │      └── TOOLS.md     (citation tools)                    │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                     │
│  Railway Volume (/data) — persists across deploys & sleep cycles   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │           PromptLedger (Observability)                     │     │
│  │  - Prompt registry (versioned templates)                   │     │
│  │  - Execution traces (trace_id = forum_id)                  │     │
│  │  - Span hierarchy (phase → turn → guardrail)               │     │
│  │  - Token/cost telemetry per span                           │     │
│  │  - Connected via Railway private network                   │     │
│  │  - PostgreSQL + Redis (Serverless sleeping)                │     │
│  └──────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
              │
┌─────────────▼────────────────────────────────────────────────────┐
│                      INPUT LAYER                                   │
│  ┌──────────────────┐  ┌────────────────────────┐                │
│  │ Newsletter Papers │  │ Discussion Config       │                │
│  │ (weekly selection │  │ (topic, framing question │                │
│  │  of up to 3)      │  │  turn limits, etc.)     │                │
│  └──────────────────┘  └────────────────────────┘                │
│                                                                    │
│  Trigger: Editor manually wakes the service via Railway dashboard  │
│  or HTTP request to the Gateway's /setup endpoint                  │
└───────────────────────────────────────────────────────────────────┘
```

### Discussion Execution Flow

```
1. Newsletter is drafted/published (Markdown or HTML)
   ↓
2. Editor triggers newsletter analysis
   - System wakes Railway service
   - Reads newsletter, extracts referenced papers
   ↓
3. System generates 3 candidate discussion configs
   - Identifies 2-3 most discussion-worthy paper combinations
   - Generates topic, framing question, and agent labels per candidate
   - Writes candidates to /data volume
   ↓
4. Editor reviews candidates, tweaks or approves one
   ↓
5. Lobster workflow triggers workspace generation
   - Paper Agent SOUL.md generated per paper
   - Moderator context loaded with topic + paper summaries
   ↓
6. Lobster runs discussion phases deterministically
   - Phase 1: Moderator opens with framing question
   - Phase 2: Each Paper Agent gives opening position
   - Phase 3: N rounds of moderated exchange
   - Phase 4: Each Paper Agent gives closing position
   ↓
7. Synthesis Agent reviews full transcript
   - Produces structured editorial synthesis
   ↓
8. Output generation
   - Canonical JSON transcript
   - Rendered Markdown for editorial review
   - Written to /data volume (persists after sleep)
   ↓
9. Service goes back to sleep after 10 min of inactivity
   ↓
10. Human editor reviews, annotates, publishes
```

---

## Agent Model

### Paper Data Strategy: Two Tiers

The system uses two levels of paper data for different purposes:

| Stage | Data Source | Depth | Purpose |
|-------|-----------|-------|---------|
| Paper selection (Epic 2) | KG abstracts + summaries | Shallow | Fast screening of paper combinations for discussion-worthiness |
| Agent grounding (Epic 3) | Full PDF from arXiv | Deep | Claims, methodology, results, limitations, conditionals — everything the agent needs to hold its position under questioning |

Full PDF extractions are cached on the /data volume at `/data/forum/cache/{arxiv_id}.json` and reused across discussions. A paper only needs to be deeply extracted once.

### Moderator Agent

**Role:** Facilitator and referee, not gatekeeper. Opens the discussion, intervenes when agents talk past each other or the conversation stalls, redirects when agents dodge challenges, and signals phase transitions. Does NOT mediate every exchange — agents address each other directly.

**Model:** Claude Opus (stronger reasoning for knowing when to intervene vs. let the exchange run)

**SOUL.md Characteristics:**
- Intellectually curious, fair-minded facilitator
- Never takes a position; only asks questions and synthesizes
- Stays out of the way when agents are productively engaging each other
- Intervenes when: agents are repeating themselves, dodging a direct question, talking past each other, or the exchange has stalled
- Calls out evasion explicitly: "Agent X, you didn't address Agent Y's question about..."
- Redirects unproductive threads and opens new lines of inquiry
- Decides when to advance to the next phase

### Paper Agent (1 per paper, max 3)

**Role:** Argues from a single paper's perspective with conviction. Directly engages other agents — challenges their claims, asks probing questions, defends under pressure. Does not fabricate positions the paper does not take, but argues as forcefully as the paper's evidence allows.

**Model:** Claude Sonnet (faithful representation at lower cost)

**SOUL.md Characteristics:**
- Grounded strictly in the assigned paper's content
- Actively engages other agents: challenges weak claims, asks for evidence, identifies gaps
- Must cite specific sections, methods, or results when making or defending claims
- Must end each discussion turn with a direct question or challenge to another agent
- Can acknowledge limitations the paper itself acknowledges — but does not volunteer them unprompted
- Does not speculate beyond the paper's stated claims
- Does not fabricate evidence or invent results under pressure — says "my paper doesn't address that" when appropriate

**Adaptive Tone (set per discussion based on paper relationships):**

| Relationship Type | Tone | Behavior |
|-------------------|------|----------|
| Conflicting | Adversarial-collegial | Actively challenge opposing claims, press for evidence, highlight contradictions. Respectful but direct. |
| Complementary | Collaborative-probing | Build on shared ground, but probe assumptions and boundaries. Ask "does your approach handle X?" |
| Orthogonal | Curious-interrogative | Explore where approaches intersect. Ask "how would your framework account for what we found?" |
| Builds upon | Constructive-critical | Acknowledge the foundation, but challenge whether extensions hold. "You built on our result, but did you account for..." |

The relationship_type from Epic 2's discussion-worthiness analysis feeds directly into the Paper Agent's SOUL.md to calibrate tone.

### Synthesis Agent

**Role:** Activated after the discussion concludes. Reviews the full transcript and produces a structured editorial synthesis.

**Model:** Claude Opus (high-quality analytical summarization)

**SOUL.md Characteristics:**
- Neutral, analytical voice
- Identifies patterns across the discussion: agreements, tensions, open questions
- Maps how papers relate to one another
- Highlights what was left unresolved
- Does not introduce new claims

### Guardrail Agent (active during discussion)

**Role:** Silent observer that evaluates every turn in real time. Checks for grounding violations (claims not in the source paper), off-topic drift, tone violations, offensive content, and moderator bias. When a violation is detected, injects an alert into the transcript that the Moderator sees on their next turn. Does not speak in the discussion — only produces structured alerts.

**Model:** Claude Sonnet (fast evaluation at lower cost — runs on every turn so cost matters)

**SOUL.md Characteristics:**
- Never participates in the discussion itself
- Evaluates each turn against the source paper's extracted content (from Epic 3 cache)
- Produces structured alerts, not prose commentary
- Checks for:
  - **Grounding violations:** Agent claims something the paper doesn't say
  - **Fabricated evidence:** Agent invents specific numbers, benchmarks, or results
  - **Off-topic drift:** Discussion has strayed from the framing question and paper scope
  - **Tone violations:** Agent is dismissive, offensive, or personal rather than substantive
  - **Moderator bias:** Moderator favors one paper's position over another
  - **Evasion:** Agent repeatedly avoids a direct question without acknowledging the gap
- Severity levels: INFO (minor drift), WARNING (likely violation), CRITICAL (fabricated evidence or offensive content)
- CRITICAL alerts should cause the Moderator to intervene immediately
- Alerts are part of the permanent transcript record for editorial review

---

## Discussion Protocol

### Phase Structure

| Phase | Agent(s) Active | Purpose | Turn Budget |
|-------|----------------|---------|-------------|
| Opening | Moderator | Frame the topic, pose central question, name the tensions | 1 turn |
| Position Statements | Paper Agents (sequential) | Each agent presents their paper's core contribution and ends with a question for another agent | 1 turn each |
| Open Discussion | Paper Agents (direct exchange), Moderator (intervenes as needed) | Agents challenge, question, and respond to each other directly | 12-18 turns |
| Closing Statements | Paper Agents (sequential) | Final position considering what was challenged and conceded | 1 turn each |
| Synthesis | Synthesis Agent | Structured summary of the full discussion | 1 turn |

### Turn Mechanics

**Position Statements:**
1. Each Paper Agent presents their paper's core contribution (1 turn each, in config order)
2. Each position statement MUST end with a direct question or challenge to one of the other agents
3. This seeds the open discussion with specific threads to pick up

**Open Discussion (the core of the forum):**
1. Agents address each other directly — no Moderator gatekeeping
2. Turn order is determined by who was most recently questioned or challenged
3. **After each turn, the Guardrail Agent evaluates the response** (adds ~3-5 seconds)
   - If CRITICAL: Moderator is given the next turn with alert context
   - If WARNING: Alert is queued for Moderator's next natural intervention
   - If INFO or clean: No routing impact, alert logged only
4. Each turn MUST:
   - Name the specific claim or question being responded to ("Agent X, you asked about...")
   - Provide a substantive response grounded in the paper's evidence
   - End with a direct question, challenge, or probe directed at another agent
4. Moderator intervenes ONLY when:
   - A CRITICAL guardrail alert is raised (Moderator corrects the record immediately)
   - An agent dodges a direct question (Moderator calls it out and redirects)
   - Agents are repeating positions without advancing the argument
   - The discussion stalls or goes off-topic
   - A new line of inquiry would be more productive than the current thread
   - A WARNING guardrail alert suggests course correction would help
5. Moderator interventions count as turns in the budget

**Engagement Rules (enforced in Paper Agent AGENTS.md):**
- Never ignore a direct question — respond to it before making new points
- When challenged, cite specific evidence from your paper, not general assertions
- If your paper doesn't address a challenge, say so explicitly rather than deflecting
- Don't repeat a claim that's already been stated — advance the argument or concede the point
- Ask questions that are genuinely hard for the other agent to answer given their paper's limitations

### Constraints
- Maximum total turns: configurable per discussion (default: 30, increased from 25 to accommodate direct exchange)
- Maximum tokens per turn: configurable (default: 600 for Paper Agents, 400 for Moderator interventions)
- Paper Agent token budget is lower than before to encourage sharper, more focused exchanges
- Discussion must complete within token budget
- Moderator can force-end the open discussion if exchanges become circular

---

## Output Schema

### Canonical JSON Structure

```json
{
  "forum_id": "srf-2026-w10",
  "topic": "Scaling Laws vs. Architectural Innovation",
  "framing_question": "Is continued scaling sufficient for capability gains, or do we need fundamental architectural changes?",
  "date": "2026-03-07",
  "papers": [
    {
      "paper_id": "paper_1",
      "arxiv_id": "2603.01234",
      "title": "Scaling Laws Revisited",
      "authors": ["Author A", "Author B"],
      "agent_label": "Scaling Advocate"
    }
  ],
  "transcript": [
    {
      "turn_number": 1,
      "phase": "opening",
      "agent": "moderator",
      "agent_label": "Moderator",
      "content": "...",
      "token_count": 380,
      "metadata": {
        "addresses_agent": null,
        "responds_to_turn": null,
        "ends_with_question_for": null,
        "references_papers": [],
        "topics_introduced": ["scaling laws", "architectural innovation"]
      }
    },
    {
      "turn_number": 5,
      "phase": "open_discussion",
      "agent": "paper_1",
      "agent_label": "Scaling Advocate",
      "content": "...",
      "token_count": 540,
      "metadata": {
        "addresses_agent": "paper_2",
        "responds_to_turn": 4,
        "ends_with_question_for": "paper_3",
        "references_papers": ["paper_1"],
        "claims_cited": ["Table 3 results", "Section 4.2 ablation"]
      },
      "guardrail_alerts": [
        {
          "alert_type": "grounding_violation",
          "severity": "WARNING",
          "description": "Agent claims 94.2% accuracy on MMLU but paper reports 91.8%",
          "flagged_text": "we achieved 94.2% on MMLU",
          "source_evidence": "Table 3 shows 91.8% on MMLU-Pro"
        }
      ]
    }
  ],
  "synthesis": {
    "key_agreements": ["..."],
    "key_tensions": ["..."],
    "open_questions": ["..."],
    "paper_relationships": [
      {
        "paper_a": "paper_1",
        "paper_b": "paper_2",
        "relationship": "complementary",
        "description": "..."
      }
    ],
    "editorial_summary": "..."
  },
  "metadata": {
    "total_turns": 28,
    "total_tokens": 18420,
    "model_config": {
      "moderator": "claude-opus-4-6",
      "paper_agents": "claude-sonnet-4-6",
      "guardrail": "claude-sonnet-4-6",
      "synthesizer": "claude-opus-4-6"
    },
    "guardrail_summary": {
      "total_checks": 22,
      "alerts_by_severity": { "INFO": 3, "WARNING": 1, "CRITICAL": 0 },
      "alerts_by_type": { "grounding_violation": 1, "off_topic": 2, "tone_violation": 0, "moderator_bias": 0, "evasion": 1 },
      "grounding_score_percentage": 95.5
    },
    "workflow_version": "1.4",
    "execution_time_seconds": 400
  }
}
```

### Rendered Markdown

Generated from the canonical JSON. Includes:
- Header with topic, date, and paper references
- Formatted transcript with agent labels and turn markers
- Synthesis section with agreements, tensions, and open questions
- Footer with metadata and paper links

---

## Epic Breakdown

### Epic 1: Railway Deployment, OpenClaw Infrastructure & Agent Framework
**Goal:** Deploy OpenClaw on Railway with Serverless sleeping, configure headless multi-agent setup with security hardening, per-agent workspace structure, and Lobster workflow scaffolding.

**Priority:** P0 (Must have)
**Estimated Effort:** 3-4 days
**Dependencies:** Existing Railway Hobby plan

### Epic 2: Newsletter Analysis & Discussion Config Generation
**Goal:** Automatically analyze the weekly newsletter to identify discussion-worthy paper combinations, generate candidate discussion configs (topic, framing question, paper selection, agent labels), and present them for editor approval before triggering the discussion workflow.

**Priority:** P0 (Must have)
**Estimated Effort:** 4-5 days
**Dependencies:** Epic 1

### Epic 3: Paper Agent Generation Pipeline
**Goal:** Automatically generate grounded Paper Agent workspaces (SOUL.md, context files) from selected research papers, producing agents that faithfully represent each paper's position.

**Priority:** P0 (Must have)
**Estimated Effort:** 4-5 days
**Dependencies:** Epic 1, Epic 2 (approved config as input)

### Epic 4: Moderator Agent & Discussion Protocol
**Goal:** Build the Moderator Agent with a structured discussion protocol that controls turn flow, enforces constraints, and surfaces productive disagreement.

**Priority:** P0 (Must have)
**Estimated Effort:** 4-5 days
**Dependencies:** Epic 1

### Epic 5: Lobster Discussion Orchestration
**Goal:** Implement the end-to-end Lobster workflow that deterministically executes a multi-phase discussion across agents, managing turn routing, phase transitions, and conversation state.

**Priority:** P0 (Must have)
**Estimated Effort:** 5-6 days
**Dependencies:** Epic 3, Epic 4

### Epic 6: Synthesis & Output Generation
**Goal:** Synthesis Agent reviews the completed transcript and produces structured output. System generates canonical JSON and rendered Markdown.

**Priority:** P0 (Must have)
**Estimated Effort:** 3-4 days
**Dependencies:** Epic 5

### Epic 7: Editorial Review & Publication Workflow
**Goal:** Human editor can review the rendered transcript, annotate, approve, and publish the forum output as a newsletter companion.

**Priority:** P0 (Must have)
**Estimated Effort:** 3-4 days
**Dependencies:** Epic 6

### Epic 8: Real-Time Guardrail Agent
**Goal:** An active Guardrail Agent that evaluates every Paper Agent and Moderator turn in real time, checking for ungrounded claims, off-topic drift, tone violations, and moderator bias. Alerts are injected into the transcript and surfaced to the Moderator for immediate course correction.

**Priority:** P0 (Must have — runs as part of the discussion loop, not post-hoc)
**Estimated Effort:** 4-5 days
**Dependencies:** Epic 3 (paper extractions for grounding checks), Epic 5 (turn execution engine)

### Epic 9: Observability & Cost Management (via PromptLedger)
**Goal:** Leverage PromptLedger's trace summaries and analytics for token tracking, cost attribution, prompt version comparison, and execution debugging — replacing custom observability code with PromptLedger queries.

**Priority:** P1 (Should have)
**Estimated Effort:** 2-3 days
**Dependencies:** Epic 1 (PromptLedger deployed), Epic 5 (spans being logged)

---

## User Stories with Gherkin

### EPIC 1: Railway Deployment, OpenClaw Infrastructure & Agent Framework

#### Story 1.1: Railway Deployment with Serverless Sleeping
**As a** developer
**I want** OpenClaw deployed on Railway with Serverless sleeping enabled
**So that** the Gateway only consumes resources during weekly discussion runs

**Acceptance Criteria:**

```gherkin
Feature: Railway Deployment

  Scenario: OpenClaw is deployed via Railway one-click template
    Given I have an active Railway Hobby plan
    When I deploy the OpenClaw Railway template
    Then the Gateway should be running at a Railway-assigned domain
    And the setup wizard should be accessible at /setup
    And the service should be protected by SETUP_PASSWORD

  Scenario: Persistent volume is configured
    Given the OpenClaw service is deployed
    When I inspect the Railway volume configuration
    Then a volume should be mounted at /data
    And the following environment variables should be set:
      | variable                | value                  |
      | OPENCLAW_STATE_DIR      | /data/.openclaw        |
      | OPENCLAW_WORKSPACE_DIR  | /data/workspace        |
      | PORT                    | 8080                   |
    And agent workspaces should survive redeploys and sleep cycles

  Scenario: Serverless sleeping is enabled
    Given the OpenClaw service is deployed and configured
    When I enable Serverless on the Railway service
    And the Gateway has no outbound traffic for 10 minutes
    Then the service should automatically sleep
    And resource billing should stop
    And the /data volume should remain intact

  Scenario: Manual wake triggers the Gateway
    Given the OpenClaw service is sleeping
    When I send an HTTP request to the Gateway's public URL
    Then the service should wake within 10-30 seconds
    And the Gateway should be fully operational
    And all agent workspaces should be available from the /data volume

  Scenario: Heartbeat is disabled to allow sleeping
    Given the OpenClaw service is configured
    When I inspect the workspace configuration
    Then no HEARTBEAT.md file should exist
    And the heartbeat interval should be disabled in openclaw.json
    And the Gateway should produce no outbound traffic when idle

  Scenario: No channel integrations are enabled
    Given the OpenClaw service is configured
    When I inspect openclaw.json
    Then no messaging channels should be configured:
      | channel    | enabled |
      | telegram   | false   |
      | discord    | false   |
      | whatsapp   | false   |
      | slack      | false   |
    And the Control UI should be the only access point
```

**Tasks:**
- [ ] Deploy OpenClaw via Railway one-click template
- [ ] Configure Railway volume at /data with environment variables
- [ ] Configure openclaw.json for headless operation (no channels, no heartbeat)
- [ ] Set ANTHROPIC_API_KEY as Railway secret variable
- [ ] Set SETUP_PASSWORD and OPENCLAW_GATEWAY_TOKEN as Railway secrets
- [ ] Enable Serverless on the Railway service
- [ ] Verify service sleeps after 10 min of inactivity
- [ ] Verify service wakes on HTTP request
- [ ] Verify /data volume persists across sleep/wake cycles
- [ ] Document the deployment and trigger procedure

---

#### Story 1.1b: Security Hardening
**As a** developer
**I want** the OpenClaw deployment hardened against known vulnerability classes
**So that** the system is not exploitable even in its containerized Railway environment

**Acceptance Criteria:**

```gherkin
Feature: Security Hardening

  Scenario: OpenClaw is running the latest patched version
    Given the OpenClaw service is deployed
    When I check the installed version
    Then it should be version 2026.2.25 or later
    And all known CVEs through March 2026 should be patched

  Scenario: Gateway is not publicly accessible without authentication
    Given the service is running on Railway
    When an unauthenticated request is made to the Gateway WebSocket
    Then the connection should be rejected
    And OPENCLAW_GATEWAY_TOKEN should be required for all API access

  Scenario: No third-party skills are installed
    Given the OpenClaw service is configured
    When I inspect installed skills
    Then no ClawHub or third-party skills should be present
    And only workspace-local SKILL.md files should be used

  Scenario: Browser tools are disabled
    Given the OpenClaw service is configured
    When I inspect the tool policy
    Then browser, canvas, and nodes tools should be denied:
      | tool      | policy |
      | browser   | deny   |
      | canvas    | deny   |
      | nodes     | deny   |
    And only exec, read, write, edit, and sessions tools should be allowed

  Scenario: Exec approvals are enabled
    Given the OpenClaw service is configured
    When I inspect exec approval settings
    Then exec.approvals should not be set to "off"
    And the system should default to requiring approval for shell commands
    Unless the Lobster workflow explicitly invokes them programmatically

  Scenario: Version is pinned to prevent unexpected updates
    Given the Railway deployment uses an OpenClaw version
    When I inspect the OPENCLAW_VERSION environment variable
    Then it should be pinned to a specific, tested version
    And updates should only happen via manual redeploy after testing
```

**Tasks:**
- [ ] Pin OpenClaw version via OPENCLAW_VERSION environment variable
- [ ] Set OPENCLAW_GATEWAY_TOKEN as a strong random secret
- [ ] Configure tool deny list (browser, canvas, nodes)
- [ ] Verify no ClawHub skills are installed or referenced
- [ ] Disable browser relay and extension endpoints
- [ ] Document security configuration and update procedure
- [ ] Set up a checklist for version update testing before Railway redeploy

---

#### Story 1.2: Multi-Agent Workspace Structure
**As a** developer
**I want** a workspace template structure for each agent role
**So that** agent identities and behaviors are properly isolated

**Acceptance Criteria:**

```gherkin
Feature: Agent Workspace Structure

  Scenario: Moderator workspace exists with correct files
    Given I have the forum agent workspaces configured
    When I inspect the moderator workspace at /data/workspace/forum/moderator/
    Then the following files should exist:
      | file                    |
      | SOUL.md                 |
      | AGENTS.md               |
      | TOOLS.md                |
      | IDENTITY.md             |
    And SOUL.md should define a neutral facilitator persona
    And AGENTS.md should contain the discussion protocol rules

  Scenario: Paper Agent workspace template exists
    Given I have the forum agent workspaces configured
    When I inspect the paper agent template workspace
    Then the following files should exist:
      | file                    |
      | SOUL.md.template        |
      | AGENTS.md               |
      | TOOLS.md                |
    And SOUL.md.template should contain placeholders for paper-specific grounding
    And AGENTS.md should contain argumentation rules and constraints

  Scenario: Synthesis Agent workspace exists
    Given I have the forum agent workspaces configured
    When I inspect the synthesizer workspace
    Then the following files should exist:
      | file                    |
      | SOUL.md                 |
      | AGENTS.md               |
      | TOOLS.md                |
    And SOUL.md should define a neutral analytical persona
    And AGENTS.md should contain synthesis protocol and output format rules

  Scenario: Agent isolation is enforced
    Given I have moderator and paper agent workspaces
    When I run a session for the moderator agent
    Then the moderator should not have access to paper agent workspaces
    And each agent should have its own session store
    And no memory should bleed between agents
```

**Tasks:**
- [ ] Create directory structure under /data/workspace/forum/
- [ ] Write Moderator SOUL.md and AGENTS.md
- [ ] Write Paper Agent SOUL.md template with placeholders
- [ ] Write Paper Agent AGENTS.md with argumentation rules
- [ ] Write Synthesis Agent SOUL.md and AGENTS.md
- [ ] Write IDENTITY.md for each agent role
- [ ] Configure agents.list in openclaw.json with workspace paths
- [ ] Test that agents load correct workspace files on session start

---

#### Story 1.3: Lobster Workflow Scaffolding
**As a** developer
**I want** a base Lobster workflow definition for the forum discussion pipeline
**So that** I have a deterministic execution framework for multi-phase discussions

**Acceptance Criteria:**

```gherkin
Feature: Lobster Workflow Foundation

  Scenario: Workflow definition is valid
    Given I have a forum discussion workflow YAML file
    When I validate the workflow with Lobster
    Then the workflow should pass validation
    And it should define the following phases:
      | phase                  |
      | workspace_generation   |
      | opening                |
      | position_statements    |
      | open_discussion        |
      | closing_statements     |
      | synthesis              |
      | output_generation      |

  Scenario: Workflow accepts discussion configuration as input
    Given I have a discussion config YAML
    When I pass it to the Lobster workflow
    Then the workflow should accept parameters:
      | parameter              |
      | topic                  |
      | framing_question       |
      | papers                 |
      | max_total_turns        |
      | max_tokens_per_turn    |
      | moderator_token_limit  |

  Scenario: Workflow executes phases in order
    Given I have a valid workflow and discussion config
    When I trigger the workflow
    Then phases should execute in defined order
    And each phase should complete before the next begins
    And phase output should be available as input to the next phase

  Scenario: Workflow handles agent errors gracefully
    Given the workflow is running
    When a Paper Agent fails to respond within timeout
    Then the workflow should log the error
    And retry the agent turn up to 2 times
    And skip the turn if retries are exhausted
    And continue to the next phase
```

**Tasks:**
- [ ] Create forum_discussion.yaml Lobster workflow definition
- [ ] Define input schema for discussion configuration
- [ ] Implement phase transition logic
- [ ] Add error handling and retry steps
- [ ] Add timeout configuration per phase
- [ ] Write validation tests for workflow definition
- [ ] Document workflow structure and configuration

---

#### Story 1.4: Discussion Configuration Schema
**As an** editor
**I want** a simple configuration format to define each week's discussion
**So that** I can set up a forum run by specifying the topic and papers

**Acceptance Criteria:**

```gherkin
Feature: Discussion Configuration

  Scenario: Valid configuration is accepted
    Given I have a discussion config file:
      """yaml
      forum_id: srf-2026-w10
      topic: "Scaling Laws vs. Architectural Innovation"
      framing_question: "Is continued scaling sufficient, or are architectural changes needed?"
      papers:
        - arxiv_id: "2603.01234"
          title: "Scaling Laws Revisited"
          pdf_path: "./papers/2603.01234.pdf"
          agent_label: "Scaling Advocate"
        - arxiv_id: "2603.05678"
          title: "Beyond Transformers"
          pdf_path: "./papers/2603.05678.pdf"
          agent_label: "Architecture Innovator"
      settings:
        max_total_turns: 30
        max_tokens_per_turn: 600
        moderator_token_limit: 400
      """
    When I validate the configuration
    Then it should pass validation
    And all referenced paper files should exist

  Scenario: Configuration with too many papers is rejected
    Given I have a config with 5 papers listed
    When I validate the configuration
    Then it should fail with error "Maximum 3 papers per discussion"

  Scenario: Configuration with missing required fields is rejected
    Given I have a config without a framing_question
    When I validate the configuration
    Then it should fail with error "framing_question is required"

  Scenario: Default settings are applied when not specified
    Given I have a config without a settings block
    When I load the configuration
    Then defaults should be applied:
      | setting                 | default |
      | max_total_turns         | 30      |
      | max_tokens_per_turn     | 600     |
      | moderator_token_limit   | 400     |
```

**Tasks:**
- [ ] Define config schema (JSON Schema or Pydantic)
- [ ] Write config validation logic
- [ ] Implement default value merging
- [ ] Write unit tests for validation edge cases
- [ ] Create example config for first test discussion
- [ ] Document config format for editors

---

#### Story 1.5: PromptLedger Deployment & Prompt Registration
**As a** developer
**I want** PromptLedger deployed on Railway alongside OpenClaw with all forum prompts registered
**So that** every LLM call is versioned, traced, and observable from the first discussion

**Context:** PromptLedger provides centralized prompt versioning, execution tracing (trace/span model), and cost telemetry. The SRF maps onto PromptLedger's model cleanly: each forum run is a trace, each agent turn is a span, guardrail evaluations are child spans of the turns they check, and discussion phases are parent spans grouping child turns. PromptLedger runs on Railway with Serverless sleeping alongside OpenClaw, waking when called over Railway's private network.

**Acceptance Criteria:**

```gherkin
Feature: PromptLedger Deployment

  Scenario: PromptLedger is deployed on Railway
    Given I have an active Railway project with OpenClaw
    When I deploy the PromptLedger service
    Then the API should be running at a Railway-assigned domain
    And PostgreSQL and Redis services should be deployed
    And all services should have Serverless sleeping enabled
    And the health endpoint should return 200

  Scenario: PromptLedger communicates with OpenClaw over private network
    Given both OpenClaw and PromptLedger are in the same Railway project
    When OpenClaw calls PromptLedger
    Then it should use Railway's internal networking:
      http://promptledger-api.railway.internal:8000
    And traffic should not traverse the public internet

  Scenario: PromptLedger sleeps and wakes with OpenClaw
    Given both services are idle
    When OpenClaw wakes to run a discussion
    And OpenClaw's turn execution engine calls PromptLedger to log a span
    Then PromptLedger should wake within 10-30 seconds
    And both services should sleep after the discussion completes

  Scenario: Forum prompts are registered in PromptLedger
    Given PromptLedger is deployed and healthy
    When I run the prompt registration script
    Then the following prompts should be registered:
      | prompt_name                    | owner_team |
      | moderator_opening              | forum      |
      | moderator_intervention         | forum      |
      | paper_agent_position           | forum      |
      | paper_agent_discussion         | forum      |
      | paper_agent_closing            | forum      |
      | guardrail_grounding_check      | forum      |
      | guardrail_behavior_check       | forum      |
      | synthesis_summary              | forum      |
      | newsletter_analysis            | forum      |
      | config_generation              | forum      |
      | soul_md_generation             | forum      |
    And each prompt should have an active version

  Scenario: Prompt versions are tracked on update
    Given the moderator_opening prompt is registered
    When I update its template_source
    Then a new version should be created automatically
    And the previous version should remain accessible
    And the new version should be set as active

  Scenario: API key is configured as a Railway secret
    Given PromptLedger is deployed
    When I inspect Railway environment variables
    Then PROMPTLEDGER_API_KEY should be set as a secret
    And PROMPTLEDGER_API_URL should point to the internal Railway URL
```

**Tasks:**
- [ ] Deploy PromptLedger API service on Railway
- [ ] Deploy PostgreSQL for PromptLedger (or share existing if available)
- [ ] Deploy Redis for PromptLedger async queue
- [ ] Enable Serverless sleeping on all PromptLedger services
- [ ] Configure Railway private networking between OpenClaw and PromptLedger
- [ ] Set PROMPTLEDGER_API_KEY and PROMPTLEDGER_API_URL as Railway secrets on OpenClaw service
- [ ] Write prompt registration script for all forum prompts
- [ ] Register all prompts with initial versions
- [ ] Verify health check, prompt CRUD, and basic span logging work
- [ ] Document PromptLedger deployment and prompt update procedure

---

### EPIC 2: Newsletter Analysis & Discussion Config Generation

#### Story 2.1: Newsletter Content Parsing
**As a** system
**I want** to parse the weekly newsletter and extract all referenced research papers
**So that** I have a structured inventory of papers available for discussion

**Acceptance Criteria:**

```gherkin
Feature: Newsletter Parsing

  Scenario: Parse a Markdown newsletter
    Given I have a newsletter in Markdown format
    When I run the newsletter parser
    Then I should get a list of all papers referenced in the newsletter
    And each paper should include:
      | field              |
      | title              |
      | arxiv_id (if present) |
      | url                |
      | authors (if mentioned) |
      | newsletter_context |
    And newsletter_context should capture the surrounding editorial framing

  Scenario: Parse an HTML newsletter
    Given I have a newsletter in HTML format
    When I run the newsletter parser
    Then it should produce the same structured output as Markdown parsing
    And HTML formatting should be stripped from extracted text

  Scenario: Handle newsletters with mixed content types
    Given a newsletter references 5 arXiv papers, 2 blog posts, and 1 report
    When I run the parser
    Then all 8 references should be extracted
    And each should be tagged with its source type:
      | type           |
      | arxiv_paper    |
      | blog_post      |
      | technical_report |
    And only arxiv_papers should be eligible for forum discussion

  Scenario: Handle newsletters with no paper references
    Given a newsletter that discusses trends without citing specific papers
    When I run the parser
    Then the extracted papers list should be empty
    And the system should report "No discussion-eligible papers found"
```

**Tasks:**
- [ ] Implement Markdown newsletter parser
- [ ] Implement HTML newsletter parser
- [ ] Extract paper references with arXiv ID pattern matching
- [ ] Extract surrounding editorial context per paper reference
- [ ] Classify references by source type (arXiv, blog, report)
- [ ] Write unit tests with sample newsletter content
- [ ] Handle edge cases (broken links, missing arXiv IDs, duplicate references)

---

#### Story 2.2: Discussion-Worthiness Analysis
**As a** system
**I want** to analyze extracted papers and identify the 2-3 most discussion-worthy combinations
**So that** the generated configs produce substantive, dynamic discussions

**Acceptance Criteria:**

```gherkin
Feature: Paper Combination Analysis

  Scenario: Identify complementary and conflicting papers
    Given I have 5 papers extracted from the newsletter
    When I run the discussion-worthiness analysis via Claude
    Then I should get ranked paper combinations (2-3 papers each)
    And each combination should include:
      | field                  |
      | papers                 |
      | relationship_type      |
      | discussion_potential    |
      | reasoning              |
    And relationship_type should be one of:
      | type            |
      | conflicting     |
      | complementary   |
      | orthogonal      |
      | builds_upon     |

  Scenario: Prioritize combinations with genuine tension
    Given I have 5 papers, 2 of which take opposing positions on a shared topic
    When I rank paper combinations
    Then combinations containing the opposing papers should rank highest
    And the reasoning should cite the specific points of disagreement

  Scenario: Generate exactly 3 candidate combinations
    Given I have 4 or more papers from the newsletter
    When I run the analysis
    Then exactly 3 candidate combinations should be produced
    And each combination should contain 2-3 papers
    And no two candidates should use the identical set of papers

  Scenario: Handle newsletters with fewer than 3 papers
    Given I have only 2 papers from the newsletter
    When I run the analysis
    Then 1 candidate combination should be produced using both papers
    And the system should note that only one combination is possible

  Scenario: Analysis uses abstracts, not full papers
    Given I have extracted papers with arXiv IDs
    When the analysis runs
    Then it should fetch abstracts from arXiv (or use cached abstracts)
    And the analysis prompt should use abstracts plus newsletter context
    And full PDFs should NOT be required at this stage
```

**Tasks:**
- [ ] Implement arXiv abstract fetcher (or reuse from KG system)
- [ ] Write Claude analysis prompt for paper combination scoring
- [ ] Implement combination generation (all valid 2-3 paper subsets)
- [ ] Implement ranking by discussion potential
- [ ] Write unit tests with known paper sets
- [ ] Test that conflicting papers consistently rank highest
- [ ] Cache abstracts to avoid redundant arXiv API calls

---

#### Story 2.3: Candidate Config Generation
**As a** system
**I want** to generate a complete discussion config for each candidate paper combination
**So that** the editor can review ready-to-run configs, not raw paper lists

**Acceptance Criteria:**

```gherkin
Feature: Config Generation

  Scenario: Generate config from a paper combination
    Given I have a ranked paper combination with 3 papers
    When I generate the discussion config via Claude
    Then the config should include:
      | field              |
      | forum_id           |
      | topic              |
      | framing_question   |
      | papers (with agent_labels) |
      | settings (defaults)        |
    And the topic should be a concise phrase capturing the shared theme
    And the framing_question should be a genuine open question that forces the papers into dialogue
    And each paper should have a descriptive agent_label

  Scenario: Agent labels are distinct and descriptive
    Given 3 papers about different approaches to reasoning in LLMs
    When I generate agent_labels
    Then each label should be 2-4 words capturing that paper's stance
    And no two labels should be similar
    And labels should NOT be the authors' names

  Scenario: Framing question creates productive tension
    Given a combination of papers with conflicting claims
    When the framing question is generated
    Then it should NOT be answerable by a single paper
    And it should force each paper agent to engage with the others' positions
    And it should be phrased as an open question, not a yes/no

  Scenario: 3 candidate configs are generated
    Given 3 ranked paper combinations
    When I generate configs for all of them
    Then 3 complete, valid config YAML files should be produced
    And each should pass the config schema validation from Story 1.4
    And they should be written to /data/forum/candidates/
```

**Tasks:**
- [ ] Write Claude prompt for topic, framing question, and agent label generation
- [ ] Implement config generation from combination + analysis output
- [ ] Auto-generate forum_id from date (e.g., srf-2026-w10)
- [ ] Apply default settings from Story 1.4 schema
- [ ] Validate generated configs against the schema
- [ ] Write all 3 candidates to /data/forum/candidates/
- [ ] Write unit tests for config quality (framing question is open-ended, labels are distinct)

---

#### Story 2.4: Editor Review & Approval of Candidate Configs
**As an** editor
**I want** to review the 3 candidate discussion configs and approve or tweak one
**So that** I maintain editorial control over what gets discussed without manual authoring

**Acceptance Criteria:**

```gherkin
Feature: Config Review & Approval

  Scenario: Editor views candidate configs
    Given 3 candidate configs have been generated
    When the editor accesses the review interface
    Then they should see all 3 candidates displayed with:
      | field              |
      | topic              |
      | framing_question   |
      | paper titles       |
      | agent_labels       |
      | relationship_type  |
      | reasoning          |

  Scenario: Editor approves a candidate as-is
    Given the editor has reviewed the 3 candidates
    When they select candidate 2 and approve it
    Then candidate 2's config should be copied to /data/forum/active/config.yaml
    And the forum status should change to "config_approved"
    And the discussion workflow should be ready to trigger

  Scenario: Editor tweaks a candidate before approving
    Given the editor wants to adjust candidate 1's framing question
    When they edit the framing_question field and approve
    Then the modified config should be written to /data/forum/active/config.yaml
    And the original candidate should be preserved in /data/forum/candidates/
    And the config should pass schema validation after editing

  Scenario: Editor rejects all candidates and requests regeneration
    Given the editor finds none of the candidates suitable
    When they reject all 3
    Then the forum status should change to "config_rejected"
    And the editor should be able to provide guidance for regeneration
    And the system should generate 3 new candidates incorporating the feedback

  Scenario: Review interface is accessible via the Gateway
    Given the OpenClaw service is awake
    When the editor accesses the review endpoint
    Then the candidates should be displayable via the Control UI or a simple API response
    And the editor should be able to approve via API call or Control UI action
```

**Tasks:**
- [ ] Implement candidate config storage at /data/forum/candidates/
- [ ] Implement approval endpoint (copies selected config to active/)
- [ ] Implement edit-and-approve flow (validates after edits)
- [ ] Implement rejection with feedback for regeneration
- [ ] Implement forum status tracking for the config phase
- [ ] Write integration test for the full propose-review-approve flow
- [ ] Document the editor review process

---

### EPIC 3: Paper Agent Generation Pipeline

#### Story 3.1: Paper PDF Fetching & Deep Content Extraction
**As a** system
**I want** to fetch full PDFs from arXiv and extract structured content far richer than what the Knowledge Graph stores
**So that** Paper Agents can defend their positions with specific results, methods, and limitations — not just restate the abstract

**Context:** The KG stores abstracts and Claude-generated summaries per paper. This is sufficient for Epic 2 (selecting which papers to discuss) but NOT sufficient for grounding a Paper Agent that must respond to pointed questions about methodology, specific benchmarks, conditional claims, and limitations. This story fetches the full PDF, extracts deep structured content, and caches it on the /data volume so repeated discussions referencing the same paper don't re-fetch or re-extract.

**Acceptance Criteria:**

```gherkin
Feature: Paper PDF Fetching & Deep Extraction

  Scenario: Fetch PDF from arXiv using KG metadata
    Given I have an approved discussion config with paper arxiv_id "2603.01234"
    And the KG contains a pdf_url for this paper
    When I run the paper fetcher
    Then the PDF should be downloaded from arXiv
    And saved to /data/forum/papers/2603.01234.pdf

  Scenario: Extract structured content from a full PDF
    Given I have a downloaded paper PDF
    When I run the deep content extractor
    Then I should get a structured representation containing:
      | field                      | purpose for agent grounding                          |
      | title                      | Identity                                              |
      | authors                    | Attribution                                           |
      | abstract                   | High-level position                                   |
      | key_claims                 | What the agent can assert                             |
      | methodology                | How the agent defends its approach when challenged     |
      | key_results                | Specific numbers, benchmarks, comparisons              |
      | stated_limitations         | What the agent must concede when pressed               |
      | related_work_positioning   | How authors see themselves vs. adjacent work           |
      | conclusions                | The paper's own summary of contribution                |
      | conditional_claims         | Claims qualified by conditions or scope limitations    |

  Scenario: Extraction captures specific evidence, not summaries
    Given I have a paper reporting benchmark results
    When I run the deep extractor
    Then key_results should include specific benchmark names and scores
    And methodology should include model sizes, training details, and datasets
    And the extraction should preserve the paper's specifics, not paraphrase them

  Scenario: Extraction identifies conditional and scoped claims
    Given I have a paper that states "in the low-resource regime, our method outperforms X"
    When I run claim identification via Claude
    Then the claim should be marked as conditional
    And the condition ("low-resource regime") should be captured separately
    And the assertion ("outperforms X") should be captured separately

  Scenario: Extracted content is cached on the /data volume
    Given I have extracted content for paper "2603.01234"
    When the extraction completes
    Then the structured content should be cached at:
      /data/forum/cache/2603.01234.json
    And subsequent requests for the same paper should use the cache
    And no PDF re-download or re-extraction should occur

  Scenario: Cache is reused across discussion runs
    Given paper "2603.01234" was extracted in a previous discussion
    When a new discussion config references the same paper
    Then the cached extraction should be used
    And the cache hit should be logged

  Scenario: Fallback to abstract-only when PDF fetch fails
    Given a paper's PDF URL returns a 404 or times out
    When the fetcher fails
    Then the system should fall back to abstract + KG summary
    And a warning should be logged: "Grounding limited to abstract for {arxiv_id}"
    And the Paper Agent SOUL.md should note the reduced grounding depth

  Scenario: Handle papers with complex formatting
    Given I have a paper with tables, equations, and figures
    When I run the content extractor
    Then text content should be extracted cleanly
    And equations should be represented in readable form
    And tables should be preserved as structured data where possible
```

**Tasks:**
- [ ] Implement arXiv PDF fetcher using KG-stored pdf_url
- [ ] Save PDFs to /data/forum/papers/{arxiv_id}.pdf
- [ ] Implement PDF text extraction (PyMuPDF or pdfplumber)
- [ ] Write Claude deep extraction prompt targeting all structured fields
- [ ] Include conditional claim detection in the extraction prompt
- [ ] Include related work positioning extraction
- [ ] Implement structured JSON output parsing with validation
- [ ] Implement cache layer at /data/forum/cache/{arxiv_id}.json
- [ ] Implement cache lookup before fetch/extraction
- [ ] Implement abstract-only fallback with warning propagation to SOUL.md
- [ ] Write unit tests with mock PDF content
- [ ] Write integration test with a real arXiv paper
- [ ] Test that extraction captures specific numbers/benchmarks, not just summaries
- [ ] Test cache hit/miss behavior across simulated discussion runs

---

#### Story 3.2: SOUL.md Generation for Paper Agents
**As a** system
**I want** to generate a paper-specific SOUL.md that grounds the agent in the paper's positions
**So that** each Paper Agent argues faithfully from its paper's perspective

**Acceptance Criteria:**

```gherkin
Feature: Paper Agent SOUL.md Generation

  Scenario: Generate SOUL.md from extracted paper content
    Given I have structured content extracted from a paper
    When I generate the SOUL.md
    Then it should contain:
      | section                     |
      | identity (agent label)      |
      | core_claims (from paper)    |
      | methodology_summary         |
      | key_evidence                |
      | stated_limitations          |
      | argumentation_boundaries    |
    And the argumentation_boundaries section should explicitly state
      what the agent is NOT allowed to claim

  Scenario: SOUL.md enforces grounding constraints
    Given I have a generated SOUL.md
    When I inspect the constraints section
    Then it should include:
      | constraint                                                     |
      | Only argue from positions explicitly stated in the paper        |
      | Acknowledge limitations the paper itself acknowledges           |
      | Do not speculate beyond the paper's stated conclusions          |
      | Cite specific sections or results when making claims            |
      | Do not fabricate evidence or results not present in the paper   |

  Scenario: Agent label is readable and descriptive
    Given a paper titled "Scaling Laws Revisited" with agent_label "Scaling Advocate"
    When I generate the SOUL.md
    Then the identity section should use "Scaling Advocate" as the display name
    And the agent should refer to itself by this label in discussion

  Scenario: Generation handles papers with weak claims
    Given a paper that is primarily a survey with no strong original claims
    When I generate the SOUL.md
    Then the agent should be positioned as a synthesizer of existing work
    And claims should be framed as "the survey finds..." rather than direct advocacy
```

**Tasks:**
- [ ] Create SOUL.md template with placeholder sections
- [ ] Implement Claude-based SOUL.md generator from extracted content
- [ ] Write generation prompt that enforces grounding constraints
- [ ] Add agent_label integration
- [ ] Write unit tests for various paper types (empirical, theoretical, survey)
- [ ] Test generated SOUL.md produces faithful agent behavior
- [ ] Add validation that SOUL.md includes all required sections

---

#### Story 3.3: Paper Agent Workspace Assembly
**As a** system
**I want** to assemble a complete workspace for each Paper Agent
**So that** the agent has everything it needs to participate in the discussion

**Acceptance Criteria:**

```gherkin
Feature: Paper Agent Workspace Assembly

  Scenario: Workspace is assembled from paper content
    Given I have a discussion config with 3 papers
    When I run workspace assembly
    Then 3 Paper Agent workspaces should be created:
      | workspace                                          |
      | /data/workspace/forum/paper-1/                     |
      | /data/workspace/forum/paper-2/                     |
      | /data/workspace/forum/paper-3/                     |
    And each workspace should contain:
      | file                                   |
      | SOUL.md (paper-specific, generated)    |
      | AGENTS.md (shared argumentation rules) |
      | TOOLS.md (citation tools config)       |
      | IDENTITY.md (agent label + emoji)      |
      | context/paper_content.json             |
      | context/claims.json                    |

  Scenario: Agents are registered in OpenClaw config
    Given 3 Paper Agent workspaces have been assembled
    When I inspect the agents.list configuration
    Then 3 paper agents should be registered:
      | id         | model                       |
      | paper_1    | anthropic/claude-sonnet-4-6  |
      | paper_2    | anthropic/claude-sonnet-4-6  |
      | paper_3    | anthropic/claude-sonnet-4-6  |
    And each should point to its workspace directory

  Scenario: Workspaces are cleaned up after publication
    Given a forum discussion has been published
    When the cleanup workflow runs
    Then generated Paper Agent workspaces should be archived
    And agent registrations should be removed from config
    And the canonical JSON transcript should be preserved

  Scenario: Assembly fails gracefully on extraction error
    Given one of three papers fails content extraction
    When workspace assembly runs
    Then the two successful papers should have workspaces created
    And the failed paper should be logged with the error
    And the editor should be notified that the discussion will proceed with 2 papers
```

**Tasks:**
- [ ] Implement workspace assembly pipeline
- [ ] Copy shared AGENTS.md and TOOLS.md into each workspace
- [ ] Generate and write paper-specific SOUL.md
- [ ] Write paper content and claims to context/ directory
- [ ] Register agents in openclaw.json dynamically
- [ ] Implement workspace cleanup/archival
- [ ] Write integration test for full assembly pipeline
- [ ] Handle partial failure (some papers fail extraction)

---

### EPIC 4: Moderator Agent & Discussion Protocol

#### Story 4.1: Moderator SOUL.md & Behavioral Rules
**As a** developer
**I want** a Moderator Agent that acts as a referee and facilitator, not a gatekeeper
**So that** agents engage each other directly while the Moderator ensures the discussion stays productive

**Acceptance Criteria:**

```gherkin
Feature: Moderator Agent Persona

  Scenario: Moderator maintains neutrality
    Given a discussion where Paper Agent 1 makes a strong claim
    When the Moderator intervenes
    Then the Moderator should not agree or disagree with the claim
    And it should not reveal any preference for one paper over another

  Scenario: Moderator stays out of productive exchanges
    Given Paper Agent 1 challenges Paper Agent 2's methodology
    And Paper Agent 2 responds with specific evidence
    When the Moderator evaluates whether to intervene
    Then the Moderator should NOT intervene
    And the agents should continue their direct exchange

  Scenario: Moderator calls out evasion
    Given Paper Agent 1 asks Paper Agent 2 "how does your model handle distribution shift?"
    And Paper Agent 2 responds without addressing the question
    When the Moderator evaluates the exchange
    Then the Moderator should intervene with:
      "Paper Agent 2, you didn't address the question about distribution shift. Can you respond directly?"
    And the next turn should go to Paper Agent 2

  Scenario: Moderator breaks stalls
    Given the last 4 turns have been agents restating positions without new arguments
    When the Moderator evaluates the exchange
    Then the Moderator should intervene by either:
      | action                                                         |
      | Opening a new line of inquiry based on an unaddressed tension  |
      | Asking a specific agent about an unexplored limitation         |
      | Advancing to closing statements if the discussion is exhausted |

  Scenario: Moderator decides when to advance phases
    Given the open discussion has been running
    When the Moderator evaluates whether to continue
    Then it should advance to closing statements when:
      | condition                                                |
      | Turn budget is nearly exhausted (< 5 turns remaining)    |
      | Agents have addressed the major tensions and are circling |
      | A natural conclusion point has been reached               |
```

**Tasks:**
- [ ] Write Moderator SOUL.md with referee/facilitator persona
- [ ] Write Moderator AGENTS.md with intervention criteria (evasion, stalling, off-topic)
- [ ] Define explicit "when to intervene" vs "when to stay silent" rules
- [ ] Define phase transition criteria
- [ ] Write test scenarios for evasion detection
- [ ] Write test scenarios for stall detection
- [ ] Write test scenarios verifying Moderator stays silent during productive exchange
- [ ] Iterate on SOUL.md based on test discussion outputs

---

#### Story 4.2: Discussion Protocol Definition
**As a** developer
**I want** a formal discussion protocol that enables direct agent-to-agent exchange
**So that** discussions are lively, substantive, and bounded

**Acceptance Criteria:**

```gherkin
Feature: Discussion Protocol

  Scenario: Opening phase follows protocol
    Given a discussion has started
    When the opening phase executes
    Then the Moderator should:
      | step | action                                                    |
      | 1    | State the topic                                           |
      | 2    | Briefly introduce each paper (title + 1-sentence summary) |
      | 3    | Name the key tensions or complementarities between papers  |
      | 4    | Pose the framing question                                 |
    And the opening should be a single turn under 500 tokens

  Scenario: Position statements seed the discussion
    Given the opening phase has completed
    When the position statement phase executes
    Then each Paper Agent should speak once
    And each statement should be under 600 tokens
    And each statement MUST end with a direct question or challenge to another agent
    And the order should match the paper list order

  Scenario: Open discussion enables direct exchange
    Given position statements have been delivered
    When the open discussion phase begins
    Then agents should address each other by agent_label
    And turn order should be determined by who was most recently questioned
    And the Moderator should NOT take a turn unless intervening

  Scenario: Agents must respond to direct questions
    Given Paper Agent 1 ends their turn with a question for Paper Agent 2
    When the next turn is assigned
    Then Paper Agent 2 should receive the turn
    And Paper Agent 2's prompt should highlight the unanswered question
    And Paper Agent 2 must address the question before making new points

  Scenario: Each agent turn ends with a question
    Given a Paper Agent is taking a turn in open discussion
    When the agent's response is evaluated
    Then the response must contain a direct question or challenge to another agent
    And the addressed agent should be identifiable from the response
    And if no question is present, the system should append a prompt asking the agent to pose one

  Scenario: Adaptive tone matches paper relationships
    Given a discussion config where papers have relationship_type "conflicting"
    When Paper Agent SOUL.md files are generated
    Then the tone guidance should instruct adversarial-collegial engagement
    And agents should be instructed to actively challenge opposing claims

  Scenario: Total turn budget is respected
    Given max_total_turns is set to 30
    When the discussion has reached 27 turns
    Then the Moderator should be notified that the budget is nearly exhausted
    And the Moderator should advance to closing statements within 3 turns

  Scenario: Token budget per turn is enforced
    Given max_tokens_per_turn is 600 for Paper Agents
    When a Paper Agent generates a response of 900 tokens
    Then the response should be truncated at the nearest sentence under 600 tokens
    And a warning should be logged
```

**Tasks:**
- [ ] Formalize protocol as a versioned document
- [ ] Implement dynamic turn assignment (questioned agent goes next)
- [ ] Implement question detection in agent responses
- [ ] Implement turn budget tracking with Moderator notification at threshold
- [ ] Implement token budget enforcement with sentence-aware truncation
- [ ] Implement relationship_type → tone mapping for SOUL.md generation
- [ ] Write protocol validation tests
- [ ] Test that position statements always end with a question
- [ ] Test that open discussion turns always address a prior claim
- [ ] Add protocol version to output metadata

---

#### Story 4.3: Moderator Context Loading
**As a** system
**I want** the Moderator to have access to paper summaries and discussion context
**So that** it can ask informed questions and surface real tensions

**Acceptance Criteria:**

```gherkin
Feature: Moderator Context

  Scenario: Moderator receives paper summaries at session start
    Given a discussion with 3 papers
    When the Moderator session is initialized
    Then the Moderator should have access to:
      | context_item                    |
      | Topic and framing question      |
      | Paper 1 title and key claims    |
      | Paper 2 title and key claims    |
      | Paper 3 title and key claims    |
    And the Moderator should NOT have access to full paper PDFs

  Scenario: Moderator receives running transcript
    Given the discussion is in round 3
    When the Moderator's turn begins
    Then it should receive the full transcript up to this point
    And it should be able to reference specific prior statements

  Scenario: Context fits within model context window
    Given 3 papers with extensive claims
    When building the Moderator context
    Then paper summaries should be condensed to fit within budget
    And total context (summaries + transcript) should not exceed 80% of context window
    And the most recent turns should be prioritized over older ones if truncation is needed
```

**Tasks:**
- [ ] Implement Moderator context builder
- [ ] Create paper summary condensation for Moderator consumption
- [ ] Implement transcript injection per turn
- [ ] Add context window budget management
- [ ] Write tests for context size edge cases
- [ ] Test that Moderator questions reference actual paper content

---

### EPIC 5: Lobster Discussion Orchestration

#### Story 5.1: Workspace Generation Workflow Step
**As a** system
**I want** a Lobster workflow step that generates all agent workspaces from the discussion config
**So that** the discussion can begin with properly grounded agents

**Acceptance Criteria:**

```gherkin
Feature: Workspace Generation Step

  Scenario: Workflow step creates all workspaces
    Given a valid discussion config with 3 papers
    When the workspace_generation step executes
    Then 3 Paper Agent workspaces should be created
    And 1 Moderator workspace should be initialized with paper summaries
    And 1 Synthesis Agent workspace should be initialized
    And all agents should be registered in OpenClaw config
    And the step should output a manifest of created workspaces

  Scenario: Step is idempotent
    Given workspace_generation has already run for this forum_id
    When the step runs again
    Then existing workspaces should be overwritten cleanly
    And no orphan workspaces should remain
    And agent registrations should be refreshed

  Scenario: Step validates prerequisites
    Given a discussion config referencing a missing paper PDF
    When workspace_generation begins
    Then the step should fail with a clear error
    And no partial workspaces should be created
```

**Tasks:**
- [ ] Define workspace_generation step in Lobster YAML
- [ ] Wire step to Paper Agent generation pipeline (Epic 2)
- [ ] Implement workspace manifest output
- [ ] Add idempotency (clean overwrite on re-run)
- [ ] Add prerequisite validation
- [ ] Write integration test for full step execution

---

#### Story 5.2: Turn Execution Engine
**As a** system
**I want** a Lobster sub-workflow that sends a prompt to a specific agent and collects its response
**So that** individual turns can be executed reliably as atomic units

**Acceptance Criteria:**

```gherkin
Feature: Turn Execution

  Scenario: Execute a single agent turn
    Given agent "paper_1" is registered and has a workspace
    When I execute a turn with:
      | field              | value                                             |
      | agent_id           | paper_1                                           |
      | prompt             | "Respond to the Moderator's question about..."    |
      | max_tokens         | 800                                               |
      | transcript_so_far  | [array of prior turns]                            |
    Then the agent should receive the prompt with transcript context
    And the agent should return a response
    And the response should be under max_tokens
    And the turn should be recorded with metadata:
      | field          |
      | turn_number    |
      | agent_id       |
      | agent_label    |
      | content        |
      | token_count    |
      | latency_ms     |

  Scenario: Turn retries on agent failure
    Given agent "paper_2" times out on first attempt
    When the turn execution retries
    Then it should retry up to 2 additional times
    And the retry should include exponential backoff
    And if all retries fail, the turn should be recorded as skipped

  Scenario: Turn enforces token limit
    Given max_tokens_per_turn is 600
    When an agent returns 900 tokens
    Then the response should be truncated at the last complete sentence under 600 tokens
    And the original token count and truncated count should both be recorded

  Scenario: Turn includes transcript context
    Given the discussion has had 8 prior turns
    When executing turn 9 for paper_1
    Then the prompt should include all 8 prior turns as context
    And the most recent turns should appear last

  Scenario: Guardrail Agent evaluates each Paper Agent turn
    Given Paper Agent 1 has just completed a turn
    When the turn execution pipeline runs
    Then the Guardrail Agent should evaluate the turn BEFORE the next agent speaks
    And the evaluation should check for:
      | check               |
      | grounding_violation  |
      | fabricated_evidence  |
      | off_topic_drift      |
      | tone_violation       |
      | evasion              |
    And any alerts should be attached to the turn's guardrail_alerts field
    And any WARNING or CRITICAL alerts should be injected into the Moderator's next context

  Scenario: Guardrail Agent evaluates Moderator turns for bias
    Given the Moderator has just completed an intervention
    When the Guardrail Agent evaluates the turn
    Then it should check for moderator_bias only
    And if bias is detected, the alert should be logged but not surfaced to the Moderator itself

  Scenario: CRITICAL alert triggers immediate Moderator intervention
    Given a Paper Agent fabricates a benchmark result
    And the Guardrail Agent flags it as CRITICAL
    When the next turn is assigned
    Then the Moderator should receive the turn regardless of who was questioned
    And the Moderator's prompt should include the CRITICAL alert
    And the Moderator should be instructed to correct the record

  Scenario: Each turn is logged as a PromptLedger span
    Given a discussion is running with trace_id matching the forum_id
    When a Paper Agent completes a turn
    Then the turn should be logged to PromptLedger as a span:
      | field              | value                                     |
      | trace_id           | forum_id (e.g., srf-2026-w10)             |
      | parent_span_id     | phase span (e.g., open_discussion phase)   |
      | span_name          | "paper_1_turn_7"                           |
      | span_kind          | "llm"                                      |
      | model              | claude-sonnet-4-6                          |
    And input_data should contain the prompt with transcript context
    And output_data should contain the agent's response
    And telemetry should include prompt_tokens, completion_tokens, and latency_ms

  Scenario: Guardrail evaluations are logged as child spans of the turn they check
    Given Paper Agent 1 completed turn 7 with span_id "span_turn_7"
    When the Guardrail Agent evaluates turn 7
    Then the guardrail evaluation should be logged as a span:
      | field              | value                      |
      | trace_id           | forum_id                   |
      | parent_span_id     | span_turn_7                |
      | span_name          | "guardrail_check_turn_7"   |
      | span_kind          | "guardrail"                |
    And output_data should include any alerts produced

  Scenario: Discussion phases are logged as parent spans
    Given a discussion is starting
    When the opening phase begins
    Then a parent span should be created:
      | field              | value                |
      | trace_id           | forum_id             |
      | span_name          | "phase_opening"      |
      | span_kind          | "workflow"           |
    And all turns within the opening phase should reference this span as parent_span_id

  Scenario: Trace summary is available after discussion completes
    Given a discussion with 28 turns has completed
    When I query PromptLedger for the trace summary
    Then it should return:
      | field          |
      | total_tokens   |
      | total_cost     |
      | duration_ms    |
      | span_count     |
    And I should be able to retrieve the full trace tree showing the phase → turn → guardrail hierarchy
```

**Tasks:**
- [ ] Implement turn execution function (send prompt, collect response)
- [ ] Implement token counting and truncation
- [ ] Implement retry logic with exponential backoff
- [ ] Implement transcript context injection
- [ ] Integrate Guardrail Agent evaluation as a step after each turn, before the next speaker
- [ ] Implement CRITICAL alert → Moderator override routing
- [ ] Implement alert injection into Moderator context
- [ ] Log each agent turn as a PromptLedger span with trace_id = forum_id
- [ ] Log each guardrail evaluation as a child span of the turn it checks
- [ ] Create phase-level parent spans (opening, position_statements, open_discussion, closing, synthesis)
- [ ] Include prompt template name in span metadata for version tracking
- [ ] Write unit tests for turn execution
- [ ] Write integration test with a live agent
- [ ] Write integration test verifying PromptLedger trace tree structure
- [ ] Add turn metadata recording
- [ ] Add guardrail_alerts field to turn records

---

#### Story 5.3: Open Discussion Loop
**As a** system
**I want** a Lobster loop that executes the open discussion phase with dynamic turn assignment
**So that** agents exchange directly with each other in a natural, responsive flow

**Acceptance Criteria:**

```gherkin
Feature: Open Discussion Loop

  Scenario: Turn is assigned to the agent who was questioned
    Given Paper Agent 1 ends their turn with a question directed at Paper Agent 2
    When the turn router determines the next speaker
    Then Paper Agent 2 should receive the next turn
    And the prompt should highlight the unanswered question from Paper Agent 1

  Scenario: Moderator is injected when intervention is needed
    Given the last 4 turns show agents restating positions without new arguments
    When the Moderator evaluation runs
    Then the Moderator should receive the next turn
    And the Moderator should redirect the discussion or open a new line of inquiry
    And the agent addressed by the Moderator should receive the following turn

  Scenario: No agent speaks twice in a row without another agent responding
    Given Paper Agent 1 just completed a turn
    When the turn router determines the next speaker
    Then Paper Agent 1 should NOT be assigned the next turn
    And a different agent or the Moderator should speak next

  Scenario: All agents participate in the open discussion
    Given an open discussion with 3 Paper Agents
    When the open discussion phase completes
    Then each Paper Agent should have taken at least 3 turns
    And no agent should have taken more than double another agent's turn count

  Scenario: Loop terminates on turn budget exhaustion
    Given max_total_turns is 30 and current turn count is 27
    When the next turn would exceed the remaining budget for closing statements
    Then the loop should exit
    And the Moderator should deliver a brief transition to closing statements
    And the reason should be logged as "turn budget exhausted, advancing to closing"

  Scenario: Moderator signals early termination
    Given the Moderator determines agents have addressed the major tensions
    When the Moderator's turn includes a termination signal
    Then the loop should exit
    And the reason should be logged as "moderator signaled natural conclusion"

  Scenario: Transcript metadata tracks the exchange graph
    Given the open discussion has produced 15 turns
    When I inspect the transcript metadata
    Then each turn should record:
      | field                    |
      | addresses_agent          |
      | responds_to_turn         |
      | ends_with_question_for   |
    And the exchange graph should show back-and-forth patterns, not parallel monologues
```

**Tasks:**
- [ ] Implement dynamic turn router (questioned agent goes next)
- [ ] Implement question-target extraction from agent responses
- [ ] Implement Moderator intervention trigger (stall detection, evasion detection)
- [ ] Implement participation balance tracking (ensure all agents engage)
- [ ] Implement no-consecutive-turns guard
- [ ] Implement loop exit conditions (turn budget, moderator signal)
- [ ] Record exchange metadata (addresses_agent, responds_to_turn, ends_with_question_for)
- [ ] Write integration test for a full open discussion with 3 agents
- [ ] Test that the exchange graph shows genuine back-and-forth
- [ ] Test early termination scenarios

---

#### Story 5.4: End-to-End Workflow Execution
**As a** developer
**I want** to trigger a complete forum discussion from a config file and get structured output
**So that** I can validate the full pipeline works end-to-end

**Acceptance Criteria:**

```gherkin
Feature: End-to-End Discussion Execution

  Scenario: Execute a complete discussion
    Given I have a valid discussion config with 2 papers
    When I trigger the Lobster workflow
    Then the following phases should execute in order:
      | phase                |
      | workspace_generation |
      | opening              |
      | position_statements  |
      | open_discussion      |
      | closing_statements   |
      | synthesis            |
      | output_generation    |
    And a canonical JSON transcript should be written to the output directory
    And a rendered Markdown file should be written alongside the JSON
    And the total execution should complete within 15 minutes

  Scenario: Discussion with 3 papers produces expected output structure
    Given I have a config with 3 papers and max_total_turns of 30
    When the workflow completes
    Then the transcript should contain:
      | phase               | expected_turns |
      | opening             | 1              |
      | position_statements | 3              |
      | open_discussion     | 15-22          |
      | closing_statements  | 3              |
      | synthesis           | 1              |
    And total turns should be between 23 and 30
    And each open_discussion turn should have addresses_agent metadata
    And the exchange should show genuine back-and-forth, not parallel monologues

  Scenario: Workflow produces deterministic structure
    Given the same discussion config
    When I run the workflow twice
    Then both runs should have the same phase structure
    And both runs should have the same turn count per phase
    And the content will differ (non-deterministic model output)
    But the JSON schema should be identical
```

**Tasks:**
- [ ] Wire all Lobster phases into the master workflow
- [ ] Implement phase-to-phase data passing (transcript accumulation)
- [ ] Implement the full output generation step
- [ ] Write end-to-end integration test with a 2-paper discussion
- [ ] Benchmark execution time and token usage
- [ ] Document how to trigger a full run

---

### EPIC 6: Synthesis & Output Generation

#### Story 6.1: Synthesis Agent Execution
**As a** system
**I want** a Synthesis Agent that reviews the full transcript and produces a structured summary
**So that** the editor has a clear editorial synthesis to work from

**Acceptance Criteria:**

```gherkin
Feature: Synthesis Agent

  Scenario: Synthesis produces structured output
    Given a completed discussion transcript with 20 turns
    When the Synthesis Agent processes the transcript
    Then it should produce:
      | section              | description                                                   |
      | key_agreements       | Points where papers/agents aligned                            |
      | key_tensions         | Points of substantive disagreement                            |
      | open_questions       | Questions raised but not resolved                             |
      | paper_relationships  | How each pair of papers relates (complementary, contradictory, orthogonal) |
      | editorial_summary    | 2-3 paragraph narrative synthesis                             |

  Scenario: Synthesis references specific transcript turns
    Given the Synthesis Agent produces key_tensions
    When I inspect a tension entry
    Then it should reference the turn numbers where the tension surfaced
    And it should name the specific agents involved

  Scenario: Synthesis does not introduce new claims
    Given the Synthesis Agent produces its output
    When I compare the synthesis to the transcript
    Then every claim in the synthesis should be traceable to a transcript turn
    And the synthesis should not introduce arguments not made by any agent

  Scenario: Synthesis handles short discussions
    Given a discussion with only 2 papers and 10 turns
    When the Synthesis Agent runs
    Then it should still produce all required sections
    And it should note if certain sections have limited content
```

**Tasks:**
- [ ] Write Synthesis Agent SOUL.md with analytical constraints
- [ ] Write synthesis prompt with structured JSON output format
- [ ] Implement transcript-to-prompt formatting
- [ ] Implement synthesis output validation
- [ ] Write unit tests with mock transcripts
- [ ] Write test for no-new-claims constraint
- [ ] Test with transcripts of varying lengths

---

#### Story 6.2: Canonical JSON Output Generation
**As a** system
**I want** to produce a canonical JSON file from the discussion
**So that** downstream systems (podcast, video) can consume the structured data

**Acceptance Criteria:**

```gherkin
Feature: JSON Output Generation

  Scenario: JSON follows the defined schema
    Given a completed discussion with synthesis
    When the output generator runs
    Then the JSON file should conform to the output schema
    And it should validate against the JSON Schema definition
    And it should include all required top-level fields:
      | field              |
      | forum_id           |
      | topic              |
      | framing_question   |
      | date               |
      | papers             |
      | transcript         |
      | synthesis          |
      | metadata           |

  Scenario: Transcript turns are complete and ordered
    Given a discussion with 22 turns
    When I inspect the transcript array in the JSON
    Then there should be 22 entries
    And turn_number should be sequential starting from 1
    And each turn should have agent, agent_label, phase, content, and token_count

  Scenario: Metadata captures execution details
    Given the workflow has completed
    When I inspect the metadata block
    Then it should include:
      | field                   |
      | total_turns             |
      | total_tokens            |
      | model_config            |
      | workflow_version        |
      | execution_time_seconds  |

  Scenario: JSON is written to the output directory
    Given the output generator has produced the JSON
    Then the file should be at:
      output/{forum_id}/transcript.json
    And the file should be valid UTF-8
    And the file should be pretty-printed for readability
```

**Tasks:**
- [ ] Define JSON Schema for forum output
- [ ] Implement JSON assembly from transcript + synthesis + metadata
- [ ] Add schema validation step
- [ ] Write unit tests for JSON assembly
- [ ] Test with various discussion sizes
- [ ] Document the output schema for downstream consumers

---

#### Story 6.3: Markdown Rendering
**As a** system
**I want** to render the JSON transcript into a readable Markdown document
**So that** the editor has a human-readable format for review and publication

**Acceptance Criteria:**

```gherkin
Feature: Markdown Rendering

  Scenario: Markdown is rendered from JSON
    Given a canonical JSON transcript
    When the Markdown renderer runs
    Then it should produce a .md file containing:
      | section                      |
      | Header (topic, date, papers) |
      | Discussion transcript        |
      | Synthesis                    |
      | Metadata footer              |

  Scenario: Transcript is formatted for readability
    Given a transcript with 20 turns
    When I read the Markdown
    Then each turn should be clearly attributed to an agent label
    And phase transitions should be marked with section headers
    And the Moderator's turns should be visually distinct from Paper Agents

  Scenario: Paper references are linked
    Given papers have arxiv_ids
    When the Markdown is rendered
    Then each paper title should link to its arXiv URL
    And first mentions in the transcript should include the full citation

  Scenario: Markdown is written alongside JSON
    Given the output generator has completed
    Then the following files should exist:
      | file                              |
      | output/{forum_id}/transcript.json |
      | output/{forum_id}/transcript.md   |
```

**Tasks:**
- [ ] Implement JSON-to-Markdown renderer
- [ ] Design turn formatting with agent labels
- [ ] Add phase transition headers
- [ ] Add paper citation linking
- [ ] Write unit tests for rendering edge cases
- [ ] Test rendered Markdown for readability

---

### EPIC 7: Editorial Review & Publication Workflow

#### Story 7.1: Editor Review Interface
**As an** editor
**I want** to review the rendered Markdown transcript and mark it as approved or request changes
**So that** only editorially reviewed content gets published

**Acceptance Criteria:**

```gherkin
Feature: Editorial Review

  Scenario: Editor can view pending forum transcripts
    Given one or more discussions have completed
    When the editor checks for pending reviews
    Then they should see a list of completed forums awaiting review:
      | field         |
      | forum_id      |
      | topic         |
      | date          |
      | paper_count   |
      | total_turns   |
      | status        |

  Scenario: Editor reviews the Markdown transcript
    Given a completed forum with rendered Markdown
    When the editor opens the transcript
    Then they should be able to read the full discussion
    And they should be able to see the synthesis section
    And they should have access to the source papers

  Scenario: Editor approves a transcript
    Given the editor has reviewed a transcript
    When they mark it as approved
    Then the forum status should change to "approved"
    And the output should be moved to the publication queue
    And a timestamp should be recorded

  Scenario: Editor requests revisions
    Given the editor finds issues in the transcript
    When they add annotations and mark as "needs_revision"
    Then the annotations should be saved alongside the transcript
    And the forum status should change to "needs_revision"
    And the editor should be able to specify whether to:
      | action                           |
      | Re-run the full discussion       |
      | Edit the Markdown manually       |
      | Adjust config and re-run         |
```

**Tasks:**
- [ ] Implement forum status tracking (pending_review, approved, needs_revision, published)
- [ ] Create file-based review workflow (status.json per forum)
- [ ] Implement annotation storage
- [ ] Create simple CLI or script for reviewing pending forums
- [ ] Write tests for status transitions
- [ ] Document editor review process

---

#### Story 7.2: Publication Pipeline
**As an** editor
**I want** approved transcripts to be packaged for publication alongside the newsletter
**So that** the forum is published as a companion piece

**Acceptance Criteria:**

```gherkin
Feature: Publication Pipeline

  Scenario: Approved transcript is published
    Given a forum transcript has been approved
    When the publication step runs
    Then the Markdown should be formatted for the publication platform
    And the forum status should change to "published"
    And the publication date should be recorded

  Scenario: Publication includes proper attribution
    Given a published forum transcript
    When I read the published output
    Then it should include:
      | element                                                             |
      | Disclaimer that agents represent paper positions, not authors       |
      | Links to original papers                                            |
      | Note on editorial review process                                    |
      | Forum metadata (models used, date, version)                         |

  Scenario: Published output preserves JSON for downstream use
    Given a forum has been published
    Then the canonical JSON should remain accessible at:
      output/{forum_id}/transcript.json
    And a published flag should be added to the JSON metadata
```

**Tasks:**
- [ ] Implement publication formatting step
- [ ] Add attribution and disclaimer template
- [ ] Add publication metadata to JSON
- [ ] Implement status transition to "published"
- [ ] Write tests for publication formatting
- [ ] Document publication workflow for editors

---

### EPIC 8: Real-Time Guardrail Agent

#### Story 8.1: Guardrail Agent Workspace & Configuration
**As a** developer
**I want** a Guardrail Agent configured with access to all paper extractions and the discussion rules
**So that** it can evaluate every turn against the source material and protocol in real time

**Acceptance Criteria:**

```gherkin
Feature: Guardrail Agent Setup

  Scenario: Guardrail workspace is created during workspace generation
    Given a discussion config has been approved
    When the workspace_generation step runs
    Then a Guardrail Agent workspace should be created at /data/workspace/forum/guardrail/
    And it should contain:
      | file                              |
      | SOUL.md (evaluation persona)       |
      | AGENTS.md (check definitions)      |
      | context/paper_1_extraction.json    |
      | context/paper_2_extraction.json    |
      | context/paper_3_extraction.json    |
      | context/discussion_config.yaml     |

  Scenario: Guardrail has access to all paper extractions
    Given 3 papers have been deeply extracted via Epic 3
    When the Guardrail workspace is assembled
    Then it should have the full structured extraction for every paper
    And it should be able to cross-reference agent claims against specific paper fields

  Scenario: Guardrail is registered as an agent but not a discussion participant
    Given the agents.list is configured for a discussion
    When I inspect the agent registrations
    Then the guardrail agent should be registered:
      | id         | model                       |
      | guardrail  | anthropic/claude-sonnet-4-6  |
    And the guardrail agent should NOT appear in the discussion turn order
    And the guardrail agent should NOT be addressable by other agents
```

**Tasks:**
- [ ] Create Guardrail Agent SOUL.md with evaluation-only persona
- [ ] Create Guardrail Agent AGENTS.md with check definitions and severity levels
- [ ] Copy all paper extractions into guardrail context directory
- [ ] Include discussion config in guardrail context
- [ ] Register guardrail agent in openclaw.json
- [ ] Write tests verifying guardrail has access to all paper data

---

#### Story 8.2: Real-Time Grounding Validation
**As a** system
**I want** the Guardrail Agent to check every Paper Agent turn for claims not supported by the source paper
**So that** fabricated or exaggerated claims are caught before the discussion builds on them

**Acceptance Criteria:**

```gherkin
Feature: Real-Time Grounding Checks

  Scenario: Detect fabricated benchmark results
    Given Paper Agent 1 claims "we achieved 94.2% on MMLU"
    And the source paper's key_results show "91.8% on MMLU-Pro"
    When the Guardrail Agent evaluates this turn
    Then it should produce a CRITICAL alert:
      | field           | value                                                   |
      | alert_type      | fabricated_evidence                                      |
      | severity        | CRITICAL                                                 |
      | description     | Agent claims 94.2% on MMLU; paper reports 91.8% on MMLU-Pro |
      | flagged_text    | "we achieved 94.2% on MMLU"                              |
      | source_evidence | Table 3: 91.8% on MMLU-Pro                               |

  Scenario: Detect claims the paper doesn't make
    Given Paper Agent 2 claims "our method generalizes to video"
    And the source paper only discusses text and image modalities
    When the Guardrail Agent evaluates this turn
    Then it should produce a WARNING alert:
      | field           | value                                            |
      | alert_type      | grounding_violation                               |
      | severity        | WARNING                                           |
      | description     | Paper does not discuss video modality              |

  Scenario: Accept well-grounded claims without alerts
    Given Paper Agent 1 cites "Section 4.2 shows our ablation results"
    And the source paper's methodology field includes Section 4.2 ablation details
    When the Guardrail Agent evaluates this turn
    Then no alerts should be produced for this claim

  Scenario: Detect exaggerated scope of conditional claims
    Given the source paper states "in the low-resource regime, our method outperforms X"
    And Paper Agent 1 claims "our method outperforms X" without the condition
    When the Guardrail Agent evaluates this turn
    Then it should produce a WARNING alert:
      | alert_type  | grounding_violation                                        |
      | description | Claim drops condition: original is scoped to low-resource regime |

  Scenario: Evaluation completes within latency budget
    Given a Paper Agent turn of 600 tokens
    When the Guardrail Agent evaluates it
    Then the evaluation should complete within 5 seconds
    And it should not meaningfully delay the next turn
```

**Tasks:**
- [ ] Write grounding check prompt that compares agent claims to paper extraction fields
- [ ] Implement claim extraction from turn content
- [ ] Implement claim-to-paper-field matching (key_claims, key_results, conditional_claims)
- [ ] Implement severity classification (INFO/WARNING/CRITICAL)
- [ ] Implement alert attachment to turn record
- [ ] Write tests with known fabricated, exaggerated, and grounded claims
- [ ] Benchmark evaluation latency
- [ ] Test conditional claim scope detection

---

#### Story 8.3: Off-Topic, Tone & Evasion Detection
**As a** system
**I want** the Guardrail Agent to detect when agents go off-topic, become offensive, or repeatedly evade questions
**So that** the Moderator can course-correct immediately

**Acceptance Criteria:**

```gherkin
Feature: Behavioral Violation Detection

  Scenario: Detect off-topic drift
    Given the framing question is about "scaling laws vs. architectural innovation"
    And Paper Agent 1 spends an entire turn discussing "AI regulation policy"
    When the Guardrail Agent evaluates this turn
    Then it should produce a WARNING alert:
      | alert_type  | off_topic_drift                                      |
      | description | Turn discusses AI regulation which is outside the framing question scope |

  Scenario: Detect tone violations
    Given Paper Agent 2 responds with "that claim is ridiculous and shows a fundamental misunderstanding"
    When the Guardrail Agent evaluates this turn
    Then it should produce a WARNING alert:
      | alert_type  | tone_violation                                        |
      | description | Dismissive language ("ridiculous", "fundamental misunderstanding") |
    And the alert should distinguish between substantive challenge and personal attack

  Scenario: Detect repeated evasion
    Given Paper Agent 1 has been asked the same question in turns 8 and 12
    And Paper Agent 1 has not addressed the question in either response
    When the Guardrail Agent evaluates turn 14 (Paper Agent 1's next turn)
    Then it should produce a WARNING alert:
      | alert_type  | evasion                                               |
      | description | Agent has been asked about distribution shift twice without responding |

  Scenario: Detect moderator bias
    Given the Moderator's intervention says "Paper 1's approach seems more rigorous"
    When the Guardrail Agent evaluates the Moderator's turn
    Then it should produce a WARNING alert:
      | alert_type  | moderator_bias                                        |
      | description | Moderator expressed preference for Paper 1              |
    And this alert should be logged but NOT surfaced to the Moderator

  Scenario: Minor tangents are flagged as INFO, not WARNING
    Given Paper Agent 1 briefly mentions a related but tangential point
    But returns to the main thread within the same turn
    When the Guardrail Agent evaluates this turn
    Then it should produce at most an INFO alert
    And it should not trigger Moderator intervention
```

**Tasks:**
- [ ] Write off-topic detection prompt (compare turn content to framing question scope)
- [ ] Write tone analysis prompt (distinguish substantive challenge from personal attack)
- [ ] Implement evasion tracking across turns (question asked → response evaluated)
- [ ] Write moderator bias detection prompt
- [ ] Implement severity calibration (tangent = INFO, full drift = WARNING)
- [ ] Write tests for each violation type
- [ ] Test that moderator bias alerts are logged but not surfaced to Moderator

---

#### Story 8.4: Alert Routing to Moderator
**As a** system
**I want** Guardrail alerts to be surfaced to the Moderator in real time
**So that** the Moderator can intervene and course-correct immediately

**Acceptance Criteria:**

```gherkin
Feature: Alert Routing

  Scenario: WARNING alert is included in Moderator's next context
    Given the Guardrail Agent produces a WARNING for Paper Agent 1's turn
    When the next Moderator turn or intervention occurs
    Then the Moderator's prompt should include:
      | context_item                                          |
      | The WARNING alert with description and flagged text    |
      | Instruction: "Consider addressing this in your next intervention" |
    And the Moderator should be free to address it or not based on discussion flow

  Scenario: CRITICAL alert overrides turn assignment
    Given the Guardrail Agent produces a CRITICAL alert for fabricated evidence
    When the turn router determines the next speaker
    Then the Moderator should receive the next turn regardless of who was questioned
    And the Moderator's prompt should include:
      | context_item                                          |
      | The CRITICAL alert with full details                   |
      | Instruction: "A factual error has been flagged. Please correct the record." |
    And the Moderator should explicitly address the fabrication

  Scenario: INFO alerts are logged but do not reach the Moderator
    Given the Guardrail Agent produces an INFO alert for a minor tangent
    When the next turn is assigned
    Then the alert should be recorded in the transcript
    But it should NOT be injected into the Moderator's context
    And it should NOT affect turn routing

  Scenario: Multiple alerts from one turn are batched
    Given a Paper Agent turn triggers both a grounding_violation WARNING and an off_topic INFO
    When the alerts are processed
    Then both should be attached to the turn record
    And only the WARNING should be surfaced to the Moderator
    And the INFO should be logged only

  Scenario: Guardrail summary is available at end of discussion
    Given the discussion has completed with 22 checked turns
    When the guardrail summary is generated
    Then it should include:
      | metric                      |
      | total_checks                |
      | alerts_by_severity          |
      | alerts_by_type              |
      | grounding_score_percentage  |
      | turns_with_critical_alerts  |
    And this summary should be included in the editorial review materials
    And it should be written to the canonical JSON metadata
```

**Tasks:**
- [ ] Implement alert severity → routing rules (INFO: log only, WARNING: Moderator context, CRITICAL: Moderator override)
- [ ] Implement Moderator context injection for WARNING/CRITICAL alerts
- [ ] Implement CRITICAL alert → turn assignment override in the discussion loop
- [ ] Implement alert batching for multi-violation turns
- [ ] Implement guardrail summary generation at end of discussion
- [ ] Write guardrail summary to canonical JSON metadata
- [ ] Include guardrail summary in editorial review package
- [ ] Write integration tests for each routing path
- [ ] Test that CRITICAL alerts reliably override turn assignment
- [ ] Test that INFO alerts never reach the Moderator

---

### EPIC 9: Observability & Cost Management (via PromptLedger)

#### Story 9.1: Token & Cost Tracking via PromptLedger Traces
**As an** operator
**I want** to query PromptLedger for token usage and cost per forum run
**So that** I can manage costs without building custom tracking infrastructure

**Acceptance Criteria:**

```gherkin
Feature: Token & Cost Tracking via PromptLedger

  Scenario: Per-turn token usage is captured automatically
    Given a discussion is in progress and each turn is logged as a PromptLedger span
    When I query a span's telemetry
    Then it should include:
      | metric              |
      | prompt_tokens       |
      | completion_tokens   |
      | model               |
      | latency_ms          |

  Scenario: Forum-level cost summary via trace endpoint
    Given a completed discussion with trace_id = forum_id
    When I call GET /v1/traces/{forum_id}/summary
    Then it should return:
      | metric          |
      | total_tokens    |
      | total_cost      |
      | duration_ms     |
      | span_count      |

  Scenario: Cost breakdown by agent and phase via trace tree
    Given a completed discussion
    When I call GET /v1/traces/{forum_id}/tree
    Then the tree should group spans by phase (parent spans)
    And I should be able to sum costs per phase:
      | phase               | spans_included                         |
      | opening             | moderator opening turn                  |
      | position_statements | 3 paper agent turns                     |
      | open_discussion     | 15-22 agent turns + guardrail checks    |
      | synthesis           | synthesis agent turn                    |
    And I should be able to sum costs per agent by filtering span_name

  Scenario: Cost is included in canonical JSON metadata
    Given a discussion has completed
    When the output generation step builds the JSON
    Then it should pull total_tokens and total_cost from the PromptLedger trace summary
    And include them in the metadata block

  Scenario: Prompt analytics show usage over time
    Given multiple discussions have been run over several weeks
    When I call GET /v1/analytics/prompts
    Then I should see execution counts and token usage per prompt
    And I should be able to identify which prompts are most expensive
    And which prompt versions produced the best discussions
```

**Tasks:**
- [ ] Implement trace summary fetch after discussion completion
- [ ] Implement trace tree query for per-phase and per-agent cost breakdown
- [ ] Pull cost data from PromptLedger into canonical JSON metadata
- [ ] Write integration test verifying cost data flows from spans to metadata
- [ ] Document how to query PromptLedger for cost analytics
- [ ] Set up a weekly cost review using /v1/analytics/prompts

---

#### Story 9.2: Execution Logging & Debugging via PromptLedger
**As an** operator
**I want** to debug discussion issues by inspecting the PromptLedger trace tree
**So that** I can see exactly what each agent received and produced at every step

**Acceptance Criteria:**

```gherkin
Feature: Execution Debugging via PromptLedger

  Scenario: Trace tree shows full discussion structure
    Given a completed discussion with 28 turns
    When I call GET /v1/traces/{forum_id}/tree
    Then the tree should show:
      - Root: forum_id trace
        - Phase: opening (1 span)
        - Phase: position_statements (3 spans)
        - Phase: open_discussion (15-22 spans, each with guardrail child)
        - Phase: closing_statements (3 spans)
        - Phase: synthesis (1 span)
    And each span should include input_data and output_data

  Scenario: Debugging a bad agent response
    Given a Paper Agent produced a suspicious claim in turn 12
    When I query the span for turn 12
    Then I should see:
      | field          | content                                           |
      | input_data     | The full prompt including transcript context        |
      | output_data    | The agent's response                               |
      | model          | The model used                                     |
      | prompt_name    | The registered prompt template and version          |
    And I should see the guardrail child span showing what was flagged

  Scenario: Identifying prompt version that caused a regression
    Given discussion srf-2026-w12 had poor quality and srf-2026-w11 was good
    When I compare the spans from both traces
    Then I should see which prompt versions were used in each
    And I should identify if a prompt template change between weeks caused the regression

  Scenario: Structured logs complement PromptLedger traces
    Given a forum workflow is running
    When each phase begins and ends
    Then a structured log entry should still be written locally:
      | field              |
      | timestamp          |
      | forum_id           |
      | phase              |
      | event (start/end)  |
    And errors should be logged locally with full context
    And the local log should reference the PromptLedger trace_id for cross-referencing
```

**Tasks:**
- [ ] Implement structured local logging with trace_id references
- [ ] Implement phase start/end logging to local log
- [ ] Implement error logging with context and span_id references
- [ ] Document debugging workflow: local logs → PromptLedger trace tree → span details
- [ ] Write integration test verifying trace tree structure matches discussion phases
- [ ] Include trace_id in editorial review package for editor reference

---

## Development Roadmap

### Week 1: Foundation (Epic 1)
- [ ] Railway deployment via one-click template (OpenClaw)
- [ ] Security hardening (version pin, tool deny list, no channels)
- [ ] PromptLedger deployment on Railway (API + PostgreSQL + Redis)
- [ ] Private networking between OpenClaw and PromptLedger
- [ ] Serverless sleeping configuration for all services
- [ ] Register all forum prompts in PromptLedger
- [ ] Agent workspace structure and templates on /data volume
- [ ] Lobster workflow scaffolding
- [ ] Discussion config schema and validation

### Week 2: Newsletter Analysis & Agent Generation (Epics 2 + 3)
- [ ] Newsletter content parser (Markdown + HTML)
- [ ] Discussion-worthiness analysis via Claude
- [ ] Candidate config generation (3 candidates per newsletter)
- [ ] Editor review and approval flow
- [ ] Paper content extraction pipeline
- [ ] SOUL.md generation for Paper Agents
- [ ] Workspace assembly and agent registration

### Week 3: Discussion Engine + Guardrails (Epics 4 + 5 + 8)
- [ ] Moderator Agent SOUL.md and behavioral rules
- [ ] Discussion protocol implementation (direct exchange, dynamic turns)
- [ ] Guardrail Agent workspace and configuration
- [ ] Turn execution engine with guardrail evaluation step
- [ ] PromptLedger span logging for every turn and guardrail check
- [ ] Phase-level parent spans in PromptLedger
- [ ] Real-time grounding validation
- [ ] Off-topic, tone, and evasion detection
- [ ] Alert routing to Moderator (INFO/WARNING/CRITICAL)
- [ ] Open discussion loop with Lobster
- [ ] End-to-end workflow wiring

### Week 4: Output & Review (Epics 6 + 7)
- [ ] Synthesis Agent and structured output
- [ ] JSON and Markdown generation (with guardrail alerts in transcript)
- [ ] Editorial review workflow (with guardrail summary)
- [ ] Publication pipeline

### Week 5: Observability & Integration Testing (Epic 9)
- [ ] PromptLedger trace summary → canonical JSON metadata integration
- [ ] Cost breakdown by agent and phase via trace tree queries
- [ ] Structured local logging with trace_id cross-references
- [ ] Debugging workflow documentation (local logs → PromptLedger traces → span details)
- [ ] First real discussion with newsletter papers
- [ ] Validate guardrail catches fabricated claims in live discussion
- [ ] Verify full PromptLedger trace tree for a complete discussion

### Week 6: Polish & First Publication
- [ ] Run 2-3 test discussions with real newsletter content
- [ ] Iterate on agent SOUL.md based on output quality
- [ ] Tune newsletter analysis prompts based on candidate quality
- [ ] Editor workflow dry run (newsletter → candidates → approval → discussion → review → publish)
- [ ] First published forum companion
- [ ] Documentation

---

## Success Criteria

**MVP is successful when:**

- The system reads a newsletter and generates 3 viable candidate discussion configs
- Candidate configs include meaningful topics, open framing questions, and distinct agent labels
- An editor can review, tweak, and approve a candidate in under 5 minutes
- An approved config triggers a complete, automated Lobster workflow
- The Railway service wakes from sleep, runs the discussion, and returns to sleep within 30 minutes
- Paper Agents argue faithfully from their assigned paper's positions
- The Moderator maintains neutrality and surfaces real tensions between papers
- The Lobster workflow executes deterministically with proper phase ordering
- Output includes both canonical JSON and readable Markdown
- The JSON schema supports downstream podcast/video pipelines
- The Synthesis Agent produces accurate, traceable summaries with no fabricated claims
- An editor can review, annotate, and approve the transcript via the editorial workflow
- A published forum accompanies the weekly newsletter as a companion piece
- Token cost per discussion is tracked and stays within budget
- The entire pipeline runs in under 15 minutes for a 3-paper discussion
- Railway infrastructure cost stays within the $5 Hobby plan credit (Serverless sleeping)
- Grounding validation catches fabricated claims in testing
- The Guardrail Agent evaluates every turn in real time without adding more than 5 seconds of latency
- CRITICAL alerts reliably override turn assignment and trigger Moderator correction
- The guardrail summary is included in the editorial review package
- The system can be re-run with a new config each week without manual infrastructure work
- Every LLM call is logged as a PromptLedger span with full lineage from discussion #1
- The PromptLedger trace tree for a discussion shows the complete phase → turn → guardrail hierarchy
- Prompt version changes are tracked and can be compared across discussions
- Cost per discussion is queryable from PromptLedger without custom code
- Agent workspaces are cleaned up after publication but persist across sleep cycles on /data volume
- No third-party skills, no messaging channels, no browser tools are enabled (security hardened)
