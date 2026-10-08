from datetime import date
from tests.crbs_env import env  # noqa: F401
async def test_dbg(env):
    _, ayse = await env.user("ayse@uni.edu.tr")
    body = {"term_id": env.term_id, "weekday": 4, "start": "08:30", "end": "09:10", "headcount": 90}
    r = await env.client.post("/api/v1/rooms/find", json=body, headers=ayse)
    out = r.json()
    print(r.status_code, out.get("closed_dates"), out.get("summary"), [ (x["code"], x["status"]) for x in out.get("results", [])][:12], out.get("slots", [])[:3], len(out.get("slots", [])))
    assert 0
