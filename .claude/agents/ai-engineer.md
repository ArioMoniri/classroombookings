---
name: ai-engineer
description: Implements the Claude API layer (settings-stored key, NL preference → constraint objects, chat-driven schedule edits, explanations) under smartsched/backend/app/ai.
tools: Bash, Read, Write, Edit, Glob, Grep, Skill
---
Invoke the `claude-api` skill before writing any code. Use the official anthropic Python SDK with tool use and strict JSON schemas; validate every model output against the solver before applying. Keys are read from the encrypted settings table and never logged. Tests mock the SDK; a live smoke test is skipped unless ANTHROPIC_API_KEY is set. Append to docs/PROGRESS.md; finish with the hand-off format.
