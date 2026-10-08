from tests.crbs_env import env  # noqa: F401
async def test_dbg(env):
    for body in ({"headcount": 150, "flex": {"other_days": True}}, {"headcount": 95, "text": "A 102", "flex": {"other_days": True}}, {"headcount": 100, "buildings": ["C"], "flex": {"other_days": True}}):
        out = (await env.client.post("/api/v1/rooms/find", json={"date": "2026-02-18", "start": 3, "end": 5, **body}, headers=env.admin)).json()
        print("ALT", body, [(a["kind"], a["code"], a["dates"], a["start_period"]) for a in out["alternatives"]], [(x["code"], x["status"]) for x in out["results"]][:4])
    assert 0
