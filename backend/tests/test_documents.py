import io

import pytest

from app import config, storage

PDF = b"%PDF-1.4\n% sample\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
CONTACT = "+91 98765 43210"

@pytest.fixture(autouse=True)
def local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "S3_BUCKET", "")
    return tmp_path

def _upload(client, ticket, tag="", name="deed.pdf", data=PDF, contact=CONTACT):
    return client.post("/api/v1/tickets/documents", data={"ticket_number": ticket, "contact": contact, "tag": tag}, files={"file": (name, io.BytesIO(data), "application/pdf")})

def _report(client, headers, ticket, **body):
    response = client.put(f"/api/v1/admin/tickets/{ticket}/report", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["report"]

def _template(client, headers, ticket):
    return client.get("/api/v1/admin/report-template", params={"ticket": ticket}, headers=headers).json()

def _item(report, tag):
    return next(i for i in report["items"] if i["tag"] == tag)

def test_customer_uploads_tags_and_downloads(client, raise_ticket, local_storage):
    ticket = raise_ticket()
    assert _upload(client, ticket, contact="+91 90000 00000").status_code == 404
    bad = _upload(client, ticket, name="virus.pdf", data=b"MZ\x90\x00")
    assert bad.status_code == 422 and "doesn't look like a PDF" in bad.json()["detail"]
    assert _upload(client, ticket, name="run.exe").status_code == 422

    view = _upload(client, ticket, tag="#Sale Deed").json()
    [doc] = view["documents"]
    assert doc["tag"] == "sale-deed" and doc["uploaded_by"] == "you" and doc["can_delete"] and view["report"] is None
    assert len(list(local_storage.rglob("*.pdf"))) == 1

    file = client.get(doc["download_url"])
    assert file.status_code == 200 and file.content == PDF and "deed.pdf" in file.headers["content-disposition"]
    assert client.get("/api/v1/files/not-a-token").status_code == 404

    retagged = client.post("/api/v1/tickets/documents/tag", json={"ticket_number": ticket, "contact": CONTACT, "document_id": doc["id"], "tag": "khata"}).json()
    assert retagged["documents"][0]["tag"] == "khata"
    gone = client.post("/api/v1/tickets/documents/delete", json={"ticket_number": ticket, "contact": CONTACT, "document_id": doc["id"]}).json()
    assert gone["documents"] == [] and list(local_storage.rglob("*.pdf")) == []

def test_preliminary_checklist_to_signed_final_report(client, raise_ticket, admin_headers):
    ticket = raise_ticket()
    template = _template(client, admin_headers, ticket)
    # Apartment checklist: deeds come from the customer, public records are fetched by Homexo from the portals.
    tags = {i["tag"]: i for i in template["items"]}
    assert tags["sale-deed"]["fetch_by"] == "customer" and tags["ec"]["fetch_by"] == "homexo" and tags["ec"]["source"] == "kaveri"
    assert "oc" in tags and "rtc" not in tags

    items = [tags["sale-deed"], tags["ec"], {"label": "Gift deed from father", "guidance": "If the seller got it by gift"}]
    # An early upload under a free tag, before the report exists.
    early = _upload(client, ticket, tag="father gift").json()["documents"][0]
    report = _report(client, admin_headers, ticket, preliminary={"observations": "Seller holds it by gift."}, items=items)
    assert report["status"] == "draft" and [i["tag"] for i in report["items"]] == ["sale-deed", "ec", "gift-deed-from-father"]
    assert client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()["report"] is None

    detail = client.post(f"/api/v1/admin/tickets/{ticket}/report/issue", headers=admin_headers).json()
    assert detail["status"] == "waiting_for_customer"
    view = client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()
    assert view["report"]["status"] == "issued" and view["report"]["sections"][2]["text"] == "Seller holds it by gift."
    assert _item(view["report"], "ec")["status_label"] == "Homexo is getting this for you" and _item(view["report"], "ec")["source"]["name"].startswith("Kaveri")
    prelim = client.get(view["report"]["preliminary_pdf_url"])
    assert prelim.status_code == 200 and prelim.content.startswith(b"%PDF")

    # Homexo's fetch queue has the EC; staff upload the copy they got from Kaveri under its tag.
    queue = client.get("/api/v1/admin/fetch-queue", headers=admin_headers).json()["items"]
    assert [(q["ticket_number"], q["item"]["tag"], q["source"]["key"]) for q in queue] == [(ticket, "ec", "kaveri")]
    client.patch(f"/api/v1/admin/tickets/{ticket}/property", json={"survey_number": "45/2"}, headers=admin_headers)
    staff = client.post(f"/api/v1/admin/tickets/{ticket}/documents", data={"tag": "ec"}, files={"file": ("ec.pdf", io.BytesIO(PDF), "application/pdf")}, headers=admin_headers).json()
    assert _item(staff["report"], "ec")["status"] == "received" and client.get("/api/v1/admin/fetch-queue", headers=admin_headers).json()["items"] == []

    # The customer links the early upload to the generated tag and adds the sale deed.
    client.post("/api/v1/tickets/documents/tag", json={"ticket_number": ticket, "contact": CONTACT, "document_id": early["id"], "tag": "gift-deed-from-father"})
    view = _upload(client, ticket, tag="sale-deed", name="sale.png", data=PNG).json()
    assert {i["tag"]: i["status"] for i in view["report"]["items"]} == {"sale-deed": "received", "ec": "received", "gift-deed-from-father": "received"}
    assert view["status"] == "under_review"

    detail = client.get(f"/api/v1/admin/tickets/{ticket}", headers=admin_headers).json()
    ids = {i["tag"]: i["id"] for i in detail["report"]["items"]}
    assert client.post(f"/api/v1/admin/tickets/{ticket}/report/final", headers=admin_headers).status_code == 409
    rejected = client.patch(f"/api/v1/admin/tickets/{ticket}/report/items/{ids['sale-deed']}", json={"status": "rejected", "note": "Page 3 is missing."}, headers=admin_headers)
    assert _item(rejected.json()["report"], "sale-deed")["status"] == "rejected"
    view = _upload(client, ticket, tag="sale-deed", name="sale-full.pdf").json()
    assert _item(view["report"], "sale-deed")["status"] == "received"

    for tag in ("sale-deed", "ec"):
        client.patch(f"/api/v1/admin/tickets/{ticket}/report/items/{ids[tag]}", json={"status": "verified"}, headers=admin_headers)
    client.patch(f"/api/v1/admin/tickets/{ticket}/report/items/{ids['gift-deed-from-father']}", json={"status": "waived", "note": "Not a gift."}, headers=admin_headers)
    # Accepted documents are locked for the customer.
    view = client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()
    sale = next(d for d in view["documents"] if d["filename"] == "sale-full.pdf")
    assert not sale["can_delete"]
    assert client.post("/api/v1/tickets/documents/delete", json={"ticket_number": ticket, "contact": CONTACT, "document_id": sale["id"]}).status_code == 409

    assert client.post(f"/api/v1/admin/tickets/{ticket}/report/final", headers=admin_headers).status_code == 422  # no opinion yet
    _report(client, admin_headers, ticket, final={"opinion": "Title is clear and marketable."})
    final = client.post(f"/api/v1/admin/tickets/{ticket}/report/final", headers=admin_headers).json()["report"]
    assert final["status"] == "final_generated" and final["final_pdf_url"]
    pdf = client.get(final["final_pdf_url"], headers=admin_headers)
    assert pdf.content.startswith(b"%PDF") and len(pdf.content) > 2000
    view = client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()
    assert view["report"]["signed_report_url"] is None and all("final" not in d["filename"] for d in view["documents"])

    signed = client.post(f"/api/v1/admin/tickets/{ticket}/report/signed", files={"file": ("scan.pdf", io.BytesIO(PDF), "application/pdf")}, headers=admin_headers).json()
    assert signed["report"]["status"] == "signed"
    view = client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()
    assert client.get(view["report"]["signed_report_url"]).content == PDF
    assert client.put(f"/api/v1/admin/tickets/{ticket}/report", json={"final": {"opinion": "x"}}, headers=admin_headers).status_code == 409
    assert "report_signed" in {e["type"] for e in signed["events"]}

def test_agents_only_reach_their_tickets(client, raise_ticket, agent):
    ticket = raise_ticket()
    assert client.put(f"/api/v1/admin/tickets/{ticket}/report", json={}, headers=agent["headers"]).status_code == 404
    assert client.get("/api/v1/admin/fetch-queue", headers=agent["headers"]).json()["items"] == []

def test_s3_storage(client, raise_ticket, monkeypatch):
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="homexo-docs")
        monkeypatch.setattr(config, "S3_BUCKET", "homexo-docs")
        monkeypatch.setattr(config, "S3_REGION", "us-east-1")
        storage._s3.cache_clear()
        ticket = raise_ticket()
        doc = _upload(client, ticket, tag="ec").json()["documents"][0]
        keys = [o["Key"] for o in boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket="homexo-docs")["Contents"]]
        assert len(keys) == 1 and keys[0].startswith(f"homexo/tickets/{ticket}/")
        redirect = client.get(doc["download_url"], follow_redirects=False)
        assert redirect.status_code == 302 and "X-Amz-Signature" in redirect.headers["location"]
        storage._s3.cache_clear()

@pytest.mark.parametrize("property_type", ["villa", "farmhouse", "plantation_estate", "industrial_land", "agricultural_land", "residential_plot"])
def test_every_kind_of_property_gets_its_checklist(client, raise_ticket, admin_headers, property_type):
    ticket = raise_ticket(property_type=property_type, service_slug="title-verification")
    items = _template(client, admin_headers, ticket)["items"]
    tags = [i["tag"] for i in items]
    assert len(tags) == len(set(tags)) and {"sale-deed", "ec"} <= set(tags)
    expected = {"villa": "rera", "farmhouse": "farm-agreement", "plantation_estate": "plantation-registration", "industrial_land": "kiadb-allotment",
                "agricultural_land": "rtc", "residential_plot": "layout-approval"}[property_type]
    assert expected in tags
    # Public records on the list go to the team to fetch, e.g. RTC from Bhoomi or Form 9/11 from e-Swathu.
    assert all(i["fetch_by"] == "homexo" for i in items if i["tag"] in ("rtc", "eswathu", "ec"))
    report = _report(client, admin_headers, ticket, items=items)
    assert len(report["items"]) == len(items)
