import copy
import uuid

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditLog, ConversationMessage, Notification, ServiceRequest, ServiceType
from app.submitted_intake import review
from conftest import authenticate_customer
from test_intake import start, submit
from test_service_intake_forms import ID, KEY, question, publish, complete

SECOND = "a26fb188-309e-4c19-94a4-e67d559219ce"
SECOND_KEY = "extra_"+uuid.UUID(SECOND).hex


def submitted(client, admin_headers):
    result = publish(client, admin_headers, questions=[question(kind="select", options=["Before signing", "After signing"]),
        question(id=SECOND, prompt="Other timing details?", kind="textarea", required=False, max_length=1000)])
    assert result.status_code == 200
    authenticate_customer(client)
    draft = complete(client, start(client, service_slug="title-verification"), **{KEY:"2", SECOND_KEY:""})
    result = submit(client, draft); assert result.status_code == 200, result.text
    return result.json()["ticket_number"]


def path(number): return f"/api/v1/admin/tickets/{number}"


def test_staff_review_retains_original_prompts_choice_labels_and_notice_versions(client, admin_headers):
    number = submitted(client, admin_headers)
    result = client.get(path(number), headers=admin_headers)
    assert result.status_code == 200 and result.headers["cache-control"] == "private, no-store"
    saved = result.json()["guided_request"]
    assert saved["format"] == "snapshot" and not saved["incomplete"] and saved["service_form_revision"] == 2
    rows = {row["key"]:row for row in saved["answers"]}
    assert rows[KEY]["answer"] == "After signing" and rows[KEY]["question"] == "When is your planned transaction?"
    assert rows[KEY]["section"] == "service" and rows[SECOND_KEY]["skipped"] is True
    assert rows["property_type"]["answer"] == "Apartment"
    assert rows["service_slug"]["answer"] == "Title Verification"
    assert saved["saving_notice"] == saved["submission_notice"] == "guided-request-v2"
    assert saved["submitted_at"] and saved["saving_consented_at"]
    assert all(set(row) == {"key","question","answer","skipped","section"} for row in saved["answers"])
    # Current catalogue wording/choices and later conversational text are not evidence of the original submission.
    assert publish(client,admin_headers,revision=2,questions=[question(prompt="New question after submission?",kind="select",options=["Changed one","Changed two"])]).status_code == 200
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==number))
        service=db.get(ServiceType,ticket.service_type_id);service.name="Renamed current service"
        db.add(ConversationMessage(conversation_id=ticket.conversation_id,sender_type="assistant",body="Later unrelated question"));db.commit()
    assert client.get(path(number),headers=admin_headers).json()["guided_request"] == saved


def test_legacy_core_values_are_distinguished_from_original_service_labels(client,admin_headers):
    number=submitted(client,admin_headers)
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==number))
        data=copy.deepcopy(ticket.structured_answers);data["guided_intake"].pop("submitted_answers");ticket.structured_answers=data;db.commit()
    saved=client.get(path(number),headers=admin_headers).json()["guided_request"]
    assert saved["format"] == "legacy" and not saved["incomplete"]
    rows={row["key"]:row for row in saved["answers"]}
    assert rows["property_type"]["answer"] == "apartment"
    assert rows["property_type"]["question"] == "Property type"
    assert rows[KEY]["answer"] == "After signing" and rows[KEY]["question"] == "When is your planned transaction?"
    assert rows[SECOND_KEY]["skipped"]


def test_case_access_applies_to_summary_and_removal_revokes_it(client,admin_headers,agent):
    number=submitted(client,admin_headers);customer=dict(client.headers)
    assert client.get(path(number)).status_code == 401
    assert client.get(path(number),headers=agent["headers"]).status_code == 404
    members=path(number)+"/members"
    assert client.post(members,headers=admin_headers,json={"user_id":agent["id"],"role":"reviewer"}).status_code == 201
    assert client.get(path(number),headers=agent["headers"]).json()["guided_request"]["answers"]
    assert client.delete(members+"/"+agent["id"],headers=admin_headers).status_code == 200
    assert client.get(path(number),headers=agent["headers"]).status_code == 404
    assert client.post(path(number)+"/assignment",headers=admin_headers,json={"agent_id":agent["id"]}).status_code == 200
    assert client.get(path(number),headers=agent["headers"]).json()["guided_request"]["format"] == "snapshot"
    assert client.post(path(number)+"/assignment",headers=admin_headers,json={"agent_id":None}).status_code == 200
    assert client.get(path(number),headers=agent["headers"]).status_code == 404
    public=client.post("/api/v1/tickets/lookup",headers=customer,json={"ticket_number":number,"contact":"9876543210"})
    assert public.status_code == 200 and "guided_request" not in public.json() and "submitted_answers" not in public.text
    account=client.get(f"/api/v1/account/requests/{number}",headers=customer)
    assert account.status_code == 200 and "guided_request" not in account.json()


def test_reading_review_does_not_mutate_submission_conversation_or_notices(client,admin_headers):
    number=submitted(client,admin_headers)
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==number))
        original=copy.deepcopy(ticket.structured_answers)
        counts=[db.scalar(select(func.count()).select_from(model)) for model in (AuditLog,ConversationMessage,Notification)]
    for _ in range(2):assert client.get(path(number),headers=admin_headers).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==number)).structured_answers == original
        assert [db.scalar(select(func.count()).select_from(model)) for model in (AuditLog,ConversationMessage,Notification)] == counts


def test_non_guided_ticket_has_no_review_panel(client,admin_headers,raise_ticket):
    number=raise_ticket()
    assert client.get(path(number),headers=admin_headers).json()["guided_request"] is None


def test_review_omits_unknown_private_metadata_and_inconsistent_snapshot_values():
    guided={"answers":{"service_slug":"title-verification","goal":"Current safe value","provider_token":"PRIVATE unknown field"},
        "submitted_answers":[{"key":"goal","question":"Original goal?","value":"PRIVATE stale value","answer":"PRIVATE stale display"},
            {"key":"provider_token","question":"PRIVATE field","value":"PRIVATE unknown field","answer":"PRIVATE unknown field"},
            {"key":"service_slug","question":"Service?","value":"title-verification","answer":"Title Verification","claim_token":"PRIVATE claim"}],
        "saving_notice_version":{"token":"PRIVATE invalid notice"},"consented_at":"bad timestamp"}
    result=review(guided)
    assert result["incomplete"] and len(result["answers"]) == 1
    assert "PRIVATE" not in str(result) and result["saving_notice"] is None and result["submitted_at"] is None


@pytest.mark.parametrize("form",[None,[],{"service_slug":"other-service","revision":2,"questions":[{"id":ID,"prompt":"PRIVATE unrelated question","kind":"text"}]},
    {"service_slug":"title-verification","revision":True,"questions":[None,4,{"id":"not-a-uuid"}]}])
def test_malformed_or_wrong_service_definitions_cannot_render_unrelated_answers(form):
    result=review({"answers":{"service_slug":"title-verification",KEY:"PRIVATE unrelated answer"},"service_form":form})
    assert result["incomplete"] and result["service_form_revision"] is None and "PRIVATE" not in str(result)


def test_legacy_skips_and_bounded_snapshot_validation_never_guess_labels():
    form={"service_slug":"title-verification","revision":2,"questions":[question(kind="select",options=["Original one","Original two"],required=False)]}
    assert review({"answers":{"service_slug":"title-verification",KEY:""},"service_form":form})["answers"][-1]["skipped"]
    invalid=review({"answers":{"service_slug":"title-verification",KEY:"9"},"service_form":form})
    assert invalid["incomplete"] and len(invalid["answers"]) == 1
    malformed=review({"answers":{"service_slug":"title-verification"},"submitted_answers":{}})
    assert malformed["incomplete"] and malformed["format"] == "legacy"
    row={"key":"service_slug","question":"Service?","value":"title-verification","answer":"Title Verification"}
    result=review({"answers":{"service_slug":"title-verification"},"submitted_answers":[row]*41})
    assert result["incomplete"] and len(result["answers"]) == 1
    assert review(None) is None and review({"answers":[]}) is None
