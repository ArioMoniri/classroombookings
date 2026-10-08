# SmartSched backend

FastAPI + SQLAlchemy + OR-Tools CP-SAT + Claude API. The developer guide lives in
[`smartsched/README.md`](../README.md); component notes are in
[`app/solver/README.md`](app/solver/README.md) and [`app/ai/README.md`](app/ai/README.md).

```bash
pip install -e ".[dev]"
make check   # ruff + mypy + pytest
make dev     # uvicorn with reload
```
