from concurrent.futures import ThreadPoolExecutor
from threading import Event
import uuid

import pytest
from sqlalchemy import func,select

from app import document_preservation as holds, document_requirements, documents, malware_scan, storage
from app.db import SessionLocal,engine
from app.models import ApiRateBucket,AuditLog,CaseDocumentHold,Document,LegalReport,ReportItem,ServiceRequest
from test_documents import CONTACT,PDF,_upload,local_storage


def endpoint(number):return f"/api/v1/admin/tickets/{number}/document-hold"


def decision(client,headers,number,held=True,reason="privacy_review",note="PRIVATE records review requires preserving these files."):
    current=client.get(endpoint(number),headers=headers).json()
    response=client.put(endpoint(number),headers=headers,json={"held":held,"revision":current["revision"],"reason":reason,"note":note})
    assert response.status_code==200,response.text
    return response.json()


@pytest.fixture
def case(client,raise_ticket,local_storage,monkeypatch):
    from app import config
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","");monkeypatch.setattr(config,"ANTHROPIC_API_KEY","")
    number=raise_ticket();response=_upload(client,number)
    assert response.status_code==201
    return number,response.json()["documents"][0]["id"]


def test_hold_blocks_customer_staff_and_direct_removal_but_keeps_reads_and_uploads(client,admin_headers,case):
    number,key=case;result=decision(client,admin_headers,number)
    assert result["held"] and result["revision"]==1 and result["history"][0]["note"].startswith("PRIVATE")
    customer=client.get(f"/api/v1/account/requests/{number}")
    assert customer.json()["document_hold"] and not customer.json()["documents"][0]["can_delete"] and "PRIVATE" not in customer.text
    assert client.get(customer.json()["documents"][0]["download_url"]).content==PDF
    body={"ticket_number":number,"contact":CONTACT,"document_id":key}
    assert client.post("/api/v1/tickets/documents/delete",json=body).status_code==409
    assert client.delete(f"/api/v1/admin/tickets/{number}/documents/{key}",headers=admin_headers).status_code==409
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==number));document=db.get(Document,uuid.UUID(key))
        with pytest.raises(holds.HTTPException):documents._remove_document(db,ticket,document)
        assert storage.get(document.storage_key)==PDF
    assert _upload(client,number,name="additional.pdf").status_code==201
    assert client.post("/api/v1/tickets/documents/tag",json={**body,"tag":"other"}).status_code==200
    released=decision(client,admin_headers,number,False,note="PRIVATE release reviewed after the records assessment.")
    assert not released["held"] and released["revision"]==2 and len(released["history"])==2
    assert client.post("/api/v1/tickets/documents/delete",json=body).status_code==200
    with SessionLocal() as db:assert db.get(Document,uuid.UUID(key)) is None


def test_case_scope_roles_private_notes_and_anonymous_cache_policy(client,admin_headers,agent,case,raise_ticket):
    number,key=case;decision(client,admin_headers,number)
    assert client.get(endpoint(number),headers={"Authorization":""}).status_code==401
    assert client.get(endpoint(number),headers={"Authorization":""}).headers["cache-control"]=="private, no-store"
    assert client.get(endpoint(number),headers=agent["headers"]).status_code==404
    client.post(f"/api/v1/admin/tickets/{number}/members",headers=admin_headers,json={"user_id":agent["id"],"role":"reviewer"})
    scoped=client.get(endpoint(number),headers=agent["headers"])
    assert scoped.status_code==200 and set(scoped.json())=={"held","revision","changed_at","can_manage"} and "PRIVATE" not in scoped.text
    assert client.put(endpoint(number),headers=agent["headers"],json={"held":False,"revision":1,"reason":"manual_review","note":"An agent cannot release this hold."}).status_code==403
    assert client.get("/api/v1/admin/document-holds",headers=agent["headers"]).status_code==403
    other=raise_ticket()
    assert not client.get(endpoint(other),headers=admin_headers).json()["held"]
    assert not _upload(client,other).json()["document_hold"]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CaseDocumentHold))==1


def test_stale_or_duplicate_release_cannot_overwrite_a_new_hold(client,admin_headers,case):
    number,_=case
    first=decision(client,admin_headers,number)
    assert client.put(endpoint(number),headers=admin_headers,json={"held":False,"revision":0,"reason":"manual_review","note":"This is an outdated release decision."}).status_code==409
    assert client.put(endpoint(number),headers=admin_headers,json={"held":True,"revision":1,"reason":"manual_review","note":"This is a duplicate hold decision."}).status_code==409
    decision(client,admin_headers,number,False);decision(client,admin_headers,number,True)
    assert client.put(endpoint(number),headers=admin_headers,json={"held":False,"revision":first["revision"],"reason":"manual_review","note":"This old release must not erase a new hold."}).status_code==409
    with SessionLocal() as db:
        assert db.scalar(select(CaseDocumentHold)).revision==3
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action.in_(holds.ACTIONS)))==3


@pytest.mark.parametrize("changes",[{"held":"true"},{"revision":True},{"revision":-1},{"reason":"other"},{"note":"too short"},{"note":"private\x00 invalid records review note"},{"extra":True}])
def test_strict_review_decisions(client,admin_headers,case,changes):
    number,_=case
    assert client.put(endpoint(number),headers=admin_headers,json={"held":True,"revision":0,"reason":"manual_review","note":"The records review needs this preservation hold.",**changes}).status_code==422
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CaseDocumentHold))==0


def test_queue_filters_counts_case_links_and_lookup_write_budgets(client,admin_headers,case,raise_ticket,monkeypatch):
    number,_=case;decision(client,admin_headers,number)
    second=raise_ticket();decision(client,admin_headers,second,reason="legal_obligation");decision(client,admin_headers,second,False,reason="manual_review")
    endpoint_queue="/api/v1/admin/document-holds"
    data=client.get(endpoint_queue,headers=admin_headers).json()
    assert data["active_count"]==1 and data["total"]==1 and data["items"][0]["ticket_number"]==number
    assert set(data["items"][0])=={"ticket_number","held","reason","revision","changed_at"}
    assert "PRIVATE" not in str(data)
    assert client.get(endpoint_queue+"?status=released&reason=manual_review",headers=admin_headers).json()["total"]==1
    assert client.get(endpoint_queue+"?status=all&q=%25",headers=admin_headers).json()["total"]==0
    assert client.get(endpoint_queue+"?status=all&page=2",headers=admin_headers).json()["items"]==[]
    for query in ("status=unknown","reason=unknown","page=0","q=bad%00query"):
        assert client.get(endpoint_queue+"?"+query,headers=admin_headers).status_code==422
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    from app import config
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(endpoint_queue,headers=admin_headers).status_code==200
    assert client.get(endpoint(number),headers=admin_headers).status_code==429
    monkeypatch.setattr(config,"API_WRITES_PER_MINUTE",1)
    payload={"held":False,"revision":1,"reason":"manual_review","note":"A deliberate reviewed release of the hold."}
    assert client.put(endpoint(number),headers=admin_headers,json=payload).status_code==200
    assert client.put(endpoint(number),headers=admin_headers,json=payload).status_code==429


def test_existing_final_file_is_not_replaced_or_orphaned_on_hold(client,admin_headers,case,monkeypatch):
    number,key=case
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==number));document=db.get(Document,uuid.UUID(key))
        document.document_category="final_report"
        report=LegalReport(service_request_id=ticket.id,status="issued",preliminary={},final={"opinion":"Reviewed synthetic opinion."},final_document_id=document.id,
            items=[ReportItem(tag="placeholder",label="Synthetic review",guidance="",fetch_by="customer",status="waived",position=0)])
        ticket.report=report;db.add(report);db.commit()
    decision(client,admin_headers,number)
    monkeypatch.setattr(documents.report_pdf,"final_pdf",lambda *args:pytest.fail("Held replacement must be rejected before PDF generation"))
    monkeypatch.setattr(storage,"put",lambda *args:pytest.fail("Held replacement must not write an orphan object"))
    response=client.post(f"/api/v1/admin/tickets/{number}/report/final",headers=admin_headers)
    assert response.status_code==409 and "preservation hold" in response.json()["detail"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Document))==1
        assert db.scalar(select(LegalReport)).final_document_id==uuid.UUID(key)


def test_hold_allows_checksum_preserving_security_scan_relocation(client,admin_headers,case,monkeypatch):
    number,key=case
    with SessionLocal() as db:
        document=db.get(Document,uuid.UUID(key));previous=document.storage_key
        document.storage_key="quarantine/"+previous;document.scan_status="failed"
        storage.put(document.storage_key,storage.get(previous),document.content_type);storage.delete(previous);db.commit()
    decision(client,admin_headers,number)
    monkeypatch.setattr(malware_scan,"scan",lambda data:malware_scan.Result("clean"))
    assert client.post(f"/api/v1/admin/tickets/{number}/documents/{key}/scan",headers=admin_headers).status_code==200
    with SessionLocal() as db:
        document=db.get(Document,uuid.UUID(key))
        assert document.scan_status=="clean" and document.storage_key==previous and storage.get(document.storage_key)==PDF
        assert db.scalar(select(CaseDocumentHold)).held


def test_file_hold_does_not_prevent_customer_withdrawal_of_ai_permission(client,admin_headers,case,monkeypatch):
    from app import config
    from test_verification import approve
    number,_=case
    monkeypatch.setattr(config,"VERIFICATION_PROCESSOR_NAME","Synthetic processor")
    monkeypatch.setattr(config,"VERIFICATION_PROCESSOR_PRIVACY_URL","https://privacy.example.test/policy")
    grant=approve(client,number);decision(client,admin_headers,number)
    response=client.put(f"/api/v1/account/requests/{number}/ai-processing",json={"allowed":False,"revision":grant["revision"]})
    assert response.status_code==200 and response.json()["status"]=="withdrawn"
    assert client.get(endpoint(number),headers=admin_headers).json()["held"]


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Real concurrent PostgreSQL case row locks")
def test_deletion_waits_for_in_progress_hold_and_then_rechecks(client,admin_headers,case):
    number,key=case;locked=Event();release=Event()
    with SessionLocal() as db:case_id=db.scalar(select(ServiceRequest.id).where(ServiceRequest.ticket_number==number))
    def place():
        with SessionLocal() as db:
            db.execute(select(ServiceRequest.id).where(ServiceRequest.id==case_id).with_for_update())
            db.add(CaseDocumentHold(service_request_id=case_id,held=True,revision=1,reason="manual_review",note="Concurrent synthetic preservation review."));db.flush()
            locked.set();assert release.wait(10);db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        placing=pool.submit(place)
        try:
            assert locked.wait(5)
            removing=pool.submit(lambda:client.delete(f"/api/v1/admin/tickets/{number}/documents/{key}",headers=admin_headers))
            assert not removing.done()
        finally:release.set()
        placing.result(timeout=10);assert removing.result(timeout=10).status_code==409
    with SessionLocal() as db:assert db.get(Document,uuid.UUID(key)) is not None
