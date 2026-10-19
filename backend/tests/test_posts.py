def _create(client, headers, **overrides):
    payload = {"post_type": "article", "title": "How to read an Encumbrance Certificate", "excerpt": "What an EC shows.", "body": "## What it is\n\nAn EC lists registered transactions.", **overrides}
    response = client.post("/api/v1/admin/posts", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()

def test_only_admins_write_posts(client, agent):
    assert client.get("/api/v1/admin/posts").status_code == 401
    assert client.post("/api/v1/admin/posts", json={"post_type": "article", "title": "Hello"}, headers=agent["headers"]).status_code == 403
    assert client.get("/api/v1/admin/posts", headers=agent["headers"]).status_code == 403

def test_drafts_stay_private_until_published(client, admin_headers):
    post = _create(client, admin_headers)
    assert post["slug"] == "how-to-read-an-encumbrance-certificate"
    assert post["status"] == "draft" and post["published_at"] is None and post["author"] == "Meera Admin"
    assert client.get("/api/v1/posts").json()["total"] == 0
    assert client.get(f"/api/v1/posts/{post['slug']}").status_code == 404

    published = client.patch(f"/api/v1/admin/posts/{post['id']}", json={"status": "published"}, headers=admin_headers).json()
    assert published["published_at"]
    public = client.get(f"/api/v1/posts/{post['slug']}").json()
    assert public["title"] == post["title"] and public["body"].startswith("## What it is") and public["reading_minutes"] == 1

    # Unpublishing hides it again but keeps the original publish date for when it comes back.
    client.patch(f"/api/v1/admin/posts/{post['id']}", json={"status": "draft"}, headers=admin_headers)
    assert client.get(f"/api/v1/posts/{post['slug']}").status_code == 404
    again = client.patch(f"/api/v1/admin/posts/{post['id']}", json={"status": "published"}, headers=admin_headers).json()
    assert again["published_at"] == published["published_at"]

def test_case_studies_filter_and_related(client, admin_headers):
    _create(client, admin_headers, status="published")
    case = _create(
        client, admin_headers, post_type="case_study", title="Whitefield apartment: a missing link in the title chain", status="published",
        tags=["Title verification", "title verification", "  Whitefield "], highlights=[{"label": "Location", "value": "Whitefield"}],
    )
    other = _create(client, admin_headers, post_type="case_study", title="JP Nagar plot khata transfer", status="published")
    assert case["tags"] == ["Title verification", "Whitefield"]

    studies = client.get("/api/v1/posts", params={"type": "case_study"}).json()
    assert studies["total"] == 2 and {p["type_label"] for p in studies["items"]} == {"Case study"}
    assert [p["slug"] for p in client.get("/api/v1/posts", params={"tag": "whitefield"}).json()["items"]] == [case["slug"]]
    assert client.get("/api/v1/posts", params={"q": "khata"}).json()["items"][0]["slug"] == other["slug"]

    detail = client.get(f"/api/v1/posts/{case['slug']}").json()
    assert detail["highlights"] == [{"label": "Location", "value": "Whitefield"}]
    assert [p["slug"] for p in detail["related"]] == [other["slug"]]

def test_slugs_are_unique(client, admin_headers):
    first = _create(client, admin_headers)
    second = _create(client, admin_headers)
    assert second["slug"] == first["slug"] + "-2"
    clash = client.patch(f"/api/v1/admin/posts/{second['id']}", json={"slug": first["slug"]}, headers=admin_headers)
    assert clash.status_code == 409
    assert client.patch(f"/api/v1/admin/posts/{second['id']}", json={"slug": "ec-explained"}, headers=admin_headers).json()["slug"] == "ec-explained"
    assert client.post("/api/v1/admin/posts", json={"post_type": "article", "title": "Bad", "slug": "Not A Slug"}, headers=admin_headers).status_code == 422

def test_cover_image_must_be_a_web_address(client, admin_headers):
    bad = client.post("/api/v1/admin/posts", json={"post_type": "article", "title": "Cover", "cover_image_url": "javascript:alert(1)"}, headers=admin_headers)
    assert bad.status_code == 422
    post = _create(client, admin_headers, cover_image_url="https://images.example.com/ec.jpg")
    cleared = client.patch(f"/api/v1/admin/posts/{post['id']}", json={"cover_image_url": ""}, headers=admin_headers).json()
    assert cleared["cover_image_url"] is None

def test_admin_list_and_delete(client, admin_headers):
    draft = _create(client, admin_headers)
    _create(client, admin_headers, post_type="case_study", title="Published study", status="published")
    listing = client.get("/api/v1/admin/posts", params={"status": "draft"}, headers=admin_headers).json()
    assert [p["id"] for p in listing["items"]] == [draft["id"]]
    assert client.delete(f"/api/v1/admin/posts/{draft['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/v1/admin/posts/{draft['id']}", headers=admin_headers).status_code == 404
    assert client.get("/api/v1/admin/posts", headers=admin_headers).json()["total"] == 1
