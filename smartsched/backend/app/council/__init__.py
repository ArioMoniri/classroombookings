"""Ingestion Council: any schedule file, any language -> typed SmartSched records, with review.

See ``docs/universal/ARCHITECTURE.md``. Entry points: :func:`app.council.orchestrator.enqueue` (run a
job), :mod:`app.council.review` (review items and decisions), :func:`app.council.commit.commit` (write
into a term).
"""
