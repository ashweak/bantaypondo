"""TEST-ONLY fixtures shaped like DPWH Transparency API records (not real data)."""
import httpx
import pytest

from app.ingestion import dpwh_api as d

API_REC = {"contractId": "99ZZ0001", "description": "Construction of Flood Control Structure, Brgy. Test, TESTTOWN, TESTPROV",
           "category": "Flood Control Structures", "componentCategories": "Flood Control and Drainage",
           "status": "On-Going", "budget": 1000000, "progress": 40,
           "location": {"province": "TESTPROV", "region": "Region X"},
           "contractor": "TEST BUILDERS (12345)", "startDate": "2025-01-01", "completionDate": "2025-06-01",
           "latitude": 8.1, "longitude": 124.2}
ROAD = {**API_REC, "contractId": "99ZZ0002", "description": "Concreting of road, Brgy. X", "category": "Roads",
        "componentCategories": "Roads"}
MIRROR = {"99ZZ0001": {**{k: None for k in d.FIELDS}, "project_code": "99ZZ0001", "abc": "1000500",
                       "source_url": d.MIRROR_URL, "source_key": "hf_flood_control_mirror"},
          "99ZZ0009": {**{k: None for k in d.FIELDS}, "project_code": "99ZZ0009", "name": "Mirror only",
                       "source_url": d.MIRROR_URL, "source_key": "hf_flood_control_mirror"}}


def test_normalize_and_merge():
    rows = {r["project_code"]: r for r in d.merge([API_REC, ROAD], MIRROR)}
    assert "99ZZ0002" not in rows                        # roads dropped
    r = rows["99ZZ0001"]
    assert r["source_url"] == "https://api.transparency.dpwh.gov.ph/projects/99ZZ0001"
    assert r["source_key"] == "dpwh_transparency"
    assert r["contractor"] == "TEST BUILDERS"            # contractor ID stripped
    assert r["abc"] == "1000500"                         # ABC filled from mirror
    assert r["target_completion"] == "2025-06-01" and r["actual_completion"] is None
    assert r["municipality"] == "TESTTOWN"
    assert rows["99ZZ0009"]["source_key"] == "hf_flood_control_mirror"   # mirror-only kept


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_paginates_and_stops():
    def h(req):
        page = int(req.url.params["page"])
        data = [API_REC] * (2 if page == 1 else 1)
        return httpx.Response(200, json={"data": {"data": data}})
    rows = d.fetch_all(limit=2, delay=0, client=_client(h))
    assert len(rows) == 3


def test_fetch_blocked_raises():
    h = lambda req: httpx.Response(403, text="Cloudflare", headers={"content-type": "text/html"})
    with pytest.raises(d.Blocked):
        d.fetch_all(delay=0, client=_client(h))
