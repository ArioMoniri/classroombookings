"""SmartSched helper ("Yardımcı"): feature index, no-AI search, action registry, cards, guard, confirm and memory.

The model never builds UI and never acts: it may choose a typed action from :mod:`app.ai.helper.actions`; the server
builds every card (:mod:`app.ai.helper.cards`) and writes run only after the person presses the card button
(:mod:`app.ai.helper.confirm`). Search and "Nerede?" work with no model at all (:mod:`app.ai.helper.index`).
Design: docs/research/2026-10-17-ai-helper-architecture.md, docs/design/v3/helper.md.
"""
