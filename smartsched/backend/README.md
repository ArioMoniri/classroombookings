# SmartSched backend

FastAPI + SQLAlchemy + OR-Tools CP-SAT + Claude API. The developer guide lives in
[`smartsched/README.md`](../README.md); component notes are in
[`app/solver/README.md`](app/solver/README.md) and [`app/ai/README.md`](app/ai/README.md).

```bash
pip install -e ".[dev]"
make check   # ruff + mypy + pytest
make dev     # uvicorn with reload
```

SAML 2.0 sign-in is built in: `signxml` (with `lxml` and `cryptography`) is a normal dependency pinned in
`requirements.lock`, so the image and pod CI ship it; regenerate the lock with the command in its header
(`uv pip compile pyproject.toml --universal --python-version 3.12 --no-annotate -o requirements.lock`).
