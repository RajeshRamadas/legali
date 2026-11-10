import concurrent.futures

import pytest
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import AuditLog, SitePolicy, SitePolicyVersion
from conftest import authenticate_customer


def content(**changes):
    return {"title": "Property service privacy notice", "summary": "How the organization handles information supplied for property services.",
        "body": "# Information and contact\n\n" + ("This is synthetic reviewed policy text used only by the test suite. " * 3).strip(),
        "organization": "Synthetic Policy Test Firm", "contact_email": "privacy@policy-fixture.in",
        "contact_phone": "", "postal_address": "Synthetic office address for testing only", "grievance_officer": "Synthetic Contact", **changes}


def save(client, headers, revision=0, kind="privacy", value=None):
    return client.put(f"/api/v1/admin/site-policies/{kind}/draft", headers=headers,
        json={"revision": revision, "content": value or content()})


def publish(client, headers, revision, kind="privacy", reviewed=True):
    return client.post(f"/api/v1/admin/site-policies/{kind}/publish", headers=headers, json={"revision": revision, "reviewed": reviewed})


def test_defaults_and_drafts_are_never_public(client, admin_headers):
    listing = client.get("/api/v1/policies")
    assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
    assert len(listing.json()["items"]) == 3 and not any(item["available"] for item in listing.json()["items"])
    result = save(client, admin_headers, value=content(body="PRIVATE_DRAFT_SENTINEL", contact_email="PRIVATE_CONTACT"))
    assert result.status_code == 200 and result.json()["revision"] == 1
    for url in ("/api/v1/policies", "/api/v1/policies/privacy", "/api/v1/policies/privacy/versions/1"):
        response = client.get(url)
        assert "PRIVATE_DRAFT_SENTINEL" not in response.text and "PRIVATE_CONTACT" not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/policies/privacy").status_code == 404


def test_only_administrators_can_read_drafts_or_change_publication(client, admin_headers, agent):
    save(client, admin_headers)
    customer = authenticate_customer(client)
    for headers in ({"Authorization": "Bearer invalid"}, agent["headers"], customer):
        for method, path, payload in (("GET", "/admin/site-policies", None),
            ("GET", "/admin/site-policies/privacy/versions", None),
            ("PUT", "/admin/site-policies/privacy/draft", {"revision": 1, "content": content()}),
            ("POST", "/admin/site-policies/privacy/publish", {"revision": 1, "reviewed": True}),
            ("POST", "/admin/site-policies/privacy/withdraw", {"revision": 1, "reviewed": True, "reason": "Synthetic withdrawal"})):
            assert client.request(method, "/api/v1" + path, headers=headers, json=payload).status_code in (401, 403)
    client.headers.pop("Authorization", None)
    assert client.get("/api/v1/admin/site-policies").status_code == 401


def test_publication_is_reviewed_versioned_and_independent_of_new_drafts(client, admin_headers):
    assert save(client, admin_headers).status_code == 200
    assert publish(client, admin_headers, 1, reviewed=False).status_code == 422
    first = publish(client, admin_headers, 1)
    assert first.status_code == 200 and first.json()["published"]["number"] == 1 and first.json()["draft"] is None
    assert publish(client, admin_headers, 2).status_code == 409
    public = client.get("/api/v1/policies/privacy").json()
    assert public["content"] == content() and public["number"] == 1
    assert public["published_at"].endswith("+00:00")
    assert "published_by_user_id" not in public and "revision" not in public
    assert save(client, admin_headers, 2, value=content(body="PRIVATE_NEXT_DRAFT")).status_code == 200
    assert client.get("/api/v1/policies/privacy").json() == public
    second_content = content(title="Updated privacy notice", body=content()["body"] + "Updated policy information.")
    assert save(client, admin_headers, 3, value=second_content).status_code == 200
    second = publish(client, admin_headers, 4)
    assert second.status_code == 200 and second.json()["published"]["number"] == 2
    assert client.get("/api/v1/policies/privacy/versions/1").json() == public
    assert client.get("/api/v1/policies/privacy").json()["content"] == second_content
    assert publish(client, admin_headers, 4).status_code == 409
    with SessionLocal() as db:
        assert len(list(db.scalars(select(SitePolicyVersion)))) == 2


@pytest.mark.parametrize("changes", [{"body": "short"}, {"summary": "short"}, {"organization": ""},
    {"contact_email": "test@example.invalid"}, {"contact_email": "test@example.com"}, {"contact_email": "test\r\nBcc: injected@firm.in"},
    {"contact_phone": "javascript:alert(1)"}, {"contact_phone": "12345"}])
def test_incomplete_or_unsafe_contacts_block_publication(client, admin_headers, changes):
    assert save(client, admin_headers, value=content(**changes)).status_code == 200
    assert publish(client, admin_headers, 1).status_code == 422
    assert client.get("/api/v1/policies/privacy").status_code == 404


def test_grievance_needs_accountable_contact_and_address(client, admin_headers):
    assert save(client, admin_headers, kind="grievance", value=content(grievance_officer="", postal_address="")).status_code == 200
    assert publish(client, admin_headers, 1, kind="grievance").status_code == 422
    assert save(client, admin_headers, 1, kind="grievance").status_code == 200
    assert publish(client, admin_headers, 2, kind="grievance").status_code == 200


def test_withdrawal_hides_current_and_all_history_and_republish_does_not_restore_it(client, admin_headers):
    save(client, admin_headers); publish(client, admin_headers, 1)
    save(client, admin_headers, 2); publish(client, admin_headers, 3)
    for reviewed, reason in ((False, "A meaningful reason"), (True, "short")):
        assert client.post("/api/v1/admin/site-policies/privacy/withdraw", headers=admin_headers,
            json={"revision": 4, "reviewed": reviewed, "reason": reason}).status_code == 422
    response = client.post("/api/v1/admin/site-policies/privacy/withdraw", headers=admin_headers,
        json={"revision": 4, "reviewed": True, "reason": "PRIVATE_WITHDRAW_REASON"})
    assert response.status_code == 200 and response.json()["published"] is None
    for path in ("/privacy", "/privacy/versions/1", "/privacy/versions/2"):
        response = client.get("/api/v1/policies" + path)
        assert response.status_code == 404 and "PRIVATE_WITHDRAW_REASON" not in response.text
    history = client.get("/api/v1/admin/site-policies/privacy/versions", headers=admin_headers).json()
    assert history["total"] == 2 and all(not item["is_public"] for item in history["items"])
    assert save(client, admin_headers, 5).status_code == 200
    assert publish(client, admin_headers, 6).json()["published"]["number"] == 3
    assert client.get("/api/v1/policies/privacy/versions/1").status_code == 404
    assert client.get("/api/v1/policies/privacy").json()["number"] == 3


def test_stale_draft_save_cannot_overwrite_or_publish_newer_work(client, admin_headers):
    save(client, admin_headers)
    before = client.get("/api/v1/admin/site-policies", headers=admin_headers).json()
    assert save(client, admin_headers, 0, value=content(title="Stale overwrite attempt")).status_code == 409
    assert publish(client, admin_headers, 0).status_code == 409
    assert client.get("/api/v1/admin/site-policies", headers=admin_headers).json() == before
    with SessionLocal() as db:
        assert db.scalar(select(SitePolicy)).revision == 1


def test_unknown_fields_control_characters_and_invalid_revisions_are_rejected(client, admin_headers):
    for payload in ({"revision": True, "content": content()}, {"revision": -1, "content": content()},
        {"revision": 0, "content": {**content(), "published": True}},
        {"revision": 0, "content": content(body="private\x00text")},
        {"revision": 0, "content": content(body="x" * 20001)}):
        assert client.put("/api/v1/admin/site-policies/privacy/draft", headers=admin_headers, json=payload).status_code == 422
    assert client.get("/api/v1/policies/unknown").status_code == 422


def test_history_pagination_and_audits_do_not_copy_private_policy_content(client, admin_headers):
    source = content(body=content()["body"] + " PRIVATE_TEXT_SENTINEL")
    revision = 0
    for _ in range(11):
        save(client, admin_headers, revision, value=source); revision += 1
        publish(client, admin_headers, revision); revision += 1
    history = client.get("/api/v1/admin/site-policies/privacy/versions?page=2", headers=admin_headers).json()
    assert history["total"] == 11 and len(history["items"]) == 1 and history["items"][0]["number"] == 1
    with SessionLocal() as db:
        audit = list(db.scalars(select(AuditLog).where(AuditLog.entity_type == "site_policy")))
        assert len(audit) == 22
        assert all("PRIVATE_TEXT_SENTINEL" not in str(row.metadata_) and source["contact_email"] not in str(row.metadata_) for row in audit)


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent policy publication requires PostgreSQL row locks")
def test_concurrent_publications_create_one_snapshot(client, admin_headers):
    save(client, admin_headers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: publish(client, admin_headers, 1).status_code, range(2)))
    assert sorted(results) == [200, 409]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(SitePolicyVersion)))) == 1
