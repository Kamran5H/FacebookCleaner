import pytest
from fastapi.testclient import TestClient

import app as server
import fb_engine as engine_mod
from fb_engine import fb_engine

LOCAL = "http://127.0.0.1:8766"
FB = "https://www.facebook.com"


def friend(slug, name=None, selected=True):
    return {"name": name or slug.title(), "url": f"{FB}/{slug}", "selected": selected}


@pytest.fixture()
def client():
    return TestClient(server.app, base_url=LOCAL)


@pytest.fixture(autouse=True)
def clean_state():
    assert str(engine_mod.DATA_CACHE_FILE).startswith(str(engine_mod.DATA_DIR))
    with fb_engine._lock:
        for k in ("friends", "groups", "pages"):
            fb_engine.data[k] = []
    fb_engine.owner_id = None
    fb_engine.owner_url = None
    yield


# --- local-only guard --------------------------------------------------------

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["version"] == server.APP_VERSION


def test_foreign_host_is_rejected():
    # DNS rebinding: evil.example resolving to 127.0.0.1 must not read your data.
    c = TestClient(server.app, base_url="http://evil.example:8766")
    assert c.get("/api/data").status_code == 403


@pytest.mark.parametrize("path", ["/api/scan", "/api/purge/resume", "/api/reset", "/api/browser/open"])
def test_cross_site_post_is_blocked(client, path):
    r = client.post(path, headers={"Origin": "https://evil.example"}, json={})
    assert r.status_code == 403


def test_facebook_origin_cannot_touch_anything_but_import(client):
    r = client.post("/api/reset", headers={"Origin": FB}, json={"confirm": True})
    assert r.status_code == 403


def test_dashboard_origin_is_allowed(client):
    r = client.post("/api/reset", headers={"Origin": LOCAL}, json={})
    assert r.status_code == 200
    assert r.json()["success"] is False  # still needs explicit confirmation


def test_import_preflight_from_facebook(client):
    r = client.options(
        "/api/import",
        headers={
            "Origin": FB,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert r.status_code == 204
    assert r.headers["access-control-allow-origin"] == FB
    assert r.headers["access-control-allow-private-network"] == "true"


# --- import / sanitation ----------------------------------------------------

def test_import_from_facebook_tab_sanitises_and_keeps_choices(client):
    fb_engine.data["friends"] = [
        {"id": f"{FB}/kept.one", "name": "Kept One", "url": f"{FB}/kept.one", "selected": False}
    ]
    payload = {"friends": [
        friend("kept.one"),                                      # previously KEEP
        friend("new.person"),
        friend("new.person"),                                    # duplicate URL
        {"name": "Phish", "url": "https://evil.example/login"},  # not Facebook
        {"name": "X", "url": f"{FB}/too.short"},                 # name too short
    ]}
    r = client.post("/api/import", headers={"Origin": FB}, json=payload)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == FB

    urls = {i["url"]: i["selected"] for i in fb_engine.data["friends"]}
    assert urls == {f"{FB}/kept.one": False, f"{FB}/new.person": True}


def test_same_name_friends_are_not_merged():
    items = fb_engine._sanitize_items(
        [friend("ali.khan.1", "Ali Khan"), friend("ali.khan.2", "Ali Khan")], "friend"
    )
    assert len(items) == 2


def test_owner_is_protected_by_id_not_name():
    fb_engine.owner_id = "1000123"
    assert fb_engine.is_protected_owner("Anyone", f"{FB}/profile.php?id=1000123")
    # A friend who merely shares the owner's name is NOT protected.
    assert not fb_engine.is_protected_owner("Kamran Ashraf", f"{FB}/some.other.kamran")


# --- purge queue --------------------------------------------------------------

@pytest.fixture()
def captured_purge(monkeypatch):
    started = {}
    monkeypatch.setattr(server.session, "start", lambda: None)
    monkeypatch.setattr(server, "_start_background", lambda fn, *a: started.setdefault("queue", a[0] if a else None))
    return started


def test_purge_only_takes_checked_items_and_skips_owner(client, captured_purge):
    fb_engine.owner_id = "42"
    fb_engine.data["friends"] = fb_engine._sanitize_items([
        friend("remove.me"),
        friend("keep.me", selected=False),
        {"name": "Me Myself", "url": f"{FB}/profile.php?id=42", "selected": True},
    ], "friend")
    # The owner is already dropped at sanitation; re-add it to prove purge also guards.
    fb_engine.data["friends"].append(
        {"id": f"{FB}/profile.php?id=42", "name": "Me Myself", "url": f"{FB}/profile.php?id=42", "selected": True}
    )
    r = client.post("/api/purge/start", json={"category": "friends"})
    assert r.json()["success"] is True
    assert [i["url"] for i in captured_purge["queue"]] == [f"{FB}/remove.me"]


def test_purge_ignores_ids_the_server_does_not_have_checked(client, captured_purge):
    fb_engine.data["friends"] = fb_engine._sanitize_items(
        [friend("a.person"), friend("b.person", selected=False)], "friend"
    )
    r = client.post("/api/purge/start", json={
        "category": "friends",
        "selected_items": [{"id": f"{FB}/b.person"}, {"id": f"{FB}/not.scanned"}],
    })
    assert r.json()["success"] is False
    assert "queue" not in captured_purge


def test_purge_with_nothing_checked(client, captured_purge):
    r = client.post("/api/purge/start", json={"category": "all"})
    assert r.json()["success"] is False


def test_reset_requires_confirmation(client):
    fb_engine.data["friends"] = fb_engine._sanitize_items([friend("still.here")], "friend")
    assert client.post("/api/reset", json={}).json()["success"] is False
    assert len(fb_engine.data["friends"]) == 1


def test_purge_history_reads_from_data_dir(client):
    engine_mod.PURGE_LOG_FILE.write_text('[{"name": "x"}]', encoding="utf-8")
    try:
        assert client.get("/api/purge/history").json()["history"] == [{"name": "x"}]
    finally:
        engine_mod.PURGE_LOG_FILE.unlink()
