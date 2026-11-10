import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import SupportRequest
from app import support, config
from conftest import authenticate_customer
from test_support import create, review, reply, BASE


def mark(client, item, revision, **kwargs):
    return client.post(f"{BASE}/{item['id']}/read", json={"through_revision": revision}, **kwargs)


def test_visible_replies_only_unread_summary_and_read_receipts_preserve_operations(client, admin_headers):
    authenticate_customer(client)
    item = create(client)
    assert item["unread_replies"] == 0
    assert client.get(BASE+"/unread").json() == {"requests": 0, "unread_replies": 0}
    private = review(client, admin_headers, item, internal_note="Private investigation, not a customer reply.").json()
    assert private["customer_update_revision"] == 0
    assert client.get(BASE+"/unread").json()["unread_replies"] == 0
    visible = review(client, admin_headers, private, customer_response="We reviewed your request and need another document.").json()
    assert visible["unread_replies"] == 1
    assert client.get(BASE).json()["items"][0]["unread_replies"] == 1
    assert client.get(f"{BASE}/{item['id']}/messages").json()["customer_update_revision"] == 1
    before = client.get(f"{BASE}/{item['id']}").json()
    read = mark(client, item, 1)
    assert read.status_code == 200 and read.json()["unread_replies"] == 0
    for key in ("revision", "updated_at", "reply_due_at", "status", "resolved_at"):
        assert read.json()[key] == before[key]
    assert mark(client, item, 1).json() == read.json()
    assert client.get(BASE+"/unread").json() == {"requests": 0, "unread_replies": 0}
    # A read receipt does not make a saved administrator draft stale.
    newer = review(client, admin_headers, before, customer_response="A second customer-visible response is now available.")
    assert newer.status_code == 200 and newer.json()["unread_replies"] == 1


def test_a_reply_arriving_after_loaded_thread_stays_unread_and_old_reads_are_monotonic(client, admin_headers):
    authenticate_customer(client); item = create(client)
    first = review(client, admin_headers, item, customer_response="Here is the initial response from the support team.").json()
    loaded = client.get(f"{BASE}/{item['id']}/messages").json()["customer_update_revision"]
    second = review(client, admin_headers, first, customer_response="A newer response arrived while you were reading.").json()
    read = mark(client, item, loaded).json()
    assert read["unread_replies"] == 1 and read["customer_update_revision"] == 2
    assert mark(client, item, 0).json()["customer_read_revision"] == 1
    assert mark(client, item, 3).status_code == 409
    assert client.get(BASE+"/unread").json() == {"requests": 1, "unread_replies": 1}
    assert mark(client, item, 2).json()["unread_replies"] == 0
    # A customer message cannot create a customer-visible staff-response alert.
    assert reply(client, item).status_code == 201
    assert client.get(f"{BASE}/{item['id']}").json()["customer_update_revision"] == 2


def test_owner_and_staff_boundaries_strict_payloads_and_private_cache(client, admin_headers, agent):
    assert client.get(BASE+"/unread").status_code == 401
    authenticate_customer(client); item = create(client); original = dict(client.headers)
    assert client.get(BASE+"/unread").headers["cache-control"] == "private, no-store"
    assert mark(client, item, 0, headers=admin_headers).status_code == 401
    assert mark(client, item, 0, headers=agent["headers"]).status_code == 401
    for body in ({"through_revision": "0"}, {"through_revision": -1}, {"through_revision": 1.0}, {"through_revision": True}, {"through_revision": 0, "extra": True}):
        assert client.post(f"{BASE}/{item['id']}/read", json=body).status_code == 422
    authenticate_customer(client, "9000000012")
    assert client.get(BASE+"/unread").json() == {"requests": 0, "unread_replies": 0}
    assert mark(client, item, 0).status_code == 404
    assert mark(client, {"id": str(uuid.uuid4())}, 0, headers=original).status_code == 404


def test_summary_counts_all_owned_requests_including_resolved_and_shared_budgets(client, admin_headers, monkeypatch):
    authenticate_customer(client); first = create(client); second = create(client)
    review(client, admin_headers, first, status="resolved", customer_response="This issue is resolved; please review the saved response.")
    response = review(client, admin_headers, second, customer_response="Another response for a separate support request.").json()
    assert client.get(BASE+"/unread").json() == {"requests": 2, "unread_replies": 2}
    assert mark(client, response, 1).status_code == 200
    assert client.get(BASE+"/unread").json() == {"requests": 1, "unread_replies": 1}
    monkeypatch.setattr(config, "API_WRITES_PER_MINUTE", 1)
    assert mark(client, first, 1).status_code == 429


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent PostgreSQL receipt and reply locking")
def test_read_waits_for_new_reply_but_marks_only_the_loaded_revision(client, admin_headers):
    authenticate_customer(client); item = create(client)
    first = review(client, admin_headers, item, customer_response="The first response has been loaded by the customer.").json()
    account_id = None
    entered = Event()
    def read_in_another_transaction():
        from app.models import CustomerAccount
        with SessionLocal() as other:
            account = other.get(CustomerAccount, account_id)
            entered.set()
            return support.read_replies(uuid.UUID(item["id"]), support.ReadReplies(through_revision=1), account, other)
    with SessionLocal() as db, ThreadPoolExecutor(max_workers=1) as pool:
        row = db.get(SupportRequest, uuid.UUID(item["id"])); account_id = row.account_id
        support.lock_account(db, account_id)
        row.customer_update_revision = 2
        db.flush()
        future = pool.submit(read_in_another_transaction)
        try:
            assert entered.wait(5)
            with pytest.raises(TimeoutError): future.result(timeout=0.2)
        finally: db.commit()
        assert future.result(timeout=5)["unread_replies"] == 1
