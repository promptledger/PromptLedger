# promptledger-client

Python client SDK for [PromptLedger](https://github.com/promptledger/PromptLedger) — a prompt registry, execution tracking, and lineage service for GenAI applications.

> **Note:** This package is currently a placeholder. The full SDK (`0.1.0`) will be released alongside PromptLedger Epic 1.

## Planned features

- `AsyncPromptLedgerClient` — async httpx wrapper for all PromptLedger API endpoints
- `PromptLedgerClient` — sync wrapper with identical interface
- `log_span()` — log LLM calls from code-based (Mode 2) workflows
- `register_code_prompts()` — register and version-track prompts defined in code
- `start_trace()` / `current_trace_id()` — contextvars helpers for multi-step trace correlation
- Structured exceptions: `AuthError`, `NotFoundError`, `PromptLedgerError`

## Installation (coming soon)

```bash
pip install promptledger-client
```
